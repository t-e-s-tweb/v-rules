// pgo_generate_test.go — PGO workload benchmarks for 0xERR0R/blocky
//
// Drop this file in the repo root (next to main.go) and run:
//
//	go test -run='^$' -bench=. -benchtime=30s -cpuprofile=default.pgo
//	go build -pgo=default.pgo .
//
// Offline-only (no upstream DNS):
//
//	go test -run='^$' \
//	    -bench='^BenchmarkPGO_(Trie|DNSMsg)$' \
//	    -benchtime=30s -cpuprofile=default.pgo
//
// ─── Design notes ────────────────────────────────────────────────────────────
//
// BenchmarkPGO_Trie
//   Exercises trie.HasParentOf — the hot inner loop of the blocking resolver.
//   No network required.
//
// BenchmarkPGO_DNSMsg
//   Exercises dns.Msg Pack/Unpack — the serialisation layer for every single
//   request and response.  No network required.
//
// BenchmarkPGO_Server
//   Starts a real blocky server on 127.0.0.1:15353 with an inline block list
//   and 1.1.1.1 as upstream.  Drives it with a realistic mix of blocked /
//   non-blocked / AAAA queries via dns.Client.
//
//   This exercises the entire hot path:
//     server.OnRequest
//       → FilteringResolver
//       → BlockingResolver  (trie lookup + response construction)
//       → CachingResolver   (cache read/write)
//       → UpstreamResolver  (parallel best, real UDP to 1.1.1.1)
//       → response encode → send
//
//   Skipped automatically when 1.1.1.1:53 is unreachable.

package main

import (
	"context"
	"fmt"
	"net"
	"strings"
	"testing"
	"time"

	"github.com/0xERR0R/blocky/config"
	"github.com/0xERR0R/blocky/server"
	"github.com/0xERR0R/blocky/trie"
	"github.com/miekg/dns"
)

// ─── helpers ─────────────────────────────────────────────────────────────────

// splitDomain splits an FQDN into (tld, rest) for use as a trie key function.
// "sub.ads.example.com" → ("com", "sub.ads.example")
func splitDomain(s string) (string, string) {
	if i := strings.LastIndexByte(s, '.'); i >= 0 {
		return s[i+1:], s[:i]
	}
	return s, ""
}

// upstreamReachable returns true when 1.1.1.1:53 answers a real DNS query.
func upstreamReachable() bool {
	// DialTimeout on UDP always succeeds (UDP is connectionless), so we must
	// actually exchange a query to confirm the host answers.
	cl := &dns.Client{Net: "udp", Timeout: 2 * time.Second}
	m := new(dns.Msg)
	m.SetQuestion("a.root-servers.net.", dns.TypeA)
	_, _, err := cl.Exchange(m, "1.1.1.1:53")
	return err == nil
}

// ─── BenchmarkPGO_Trie ───────────────────────────────────────────────────────

// BenchmarkPGO_Trie is the most valuable PGO benchmark because the trie hot
// loop runs on *every* DNS query (both blocked and clean).
//
// Population: 45 000 entries (≈ mid-size production block list).
// Query mix:  ~20 % blocked sub-domains, ~80 % clean.
func BenchmarkPGO_Trie(b *testing.B) {
	t := trie.NewTrie(splitDomain)

	// Populate three commonly blocked TLD patterns.
	for i := 0; i < 15_000; i++ {
		t.Insert(fmt.Sprintf("ad-%d.example.com", i))
		t.Insert(fmt.Sprintf("tracker-%d.net", i))
		t.Insert(fmt.Sprintf("malware-%d.io", i))
	}

	domains := make([]string, 500)
	for i := range domains {
		switch i % 10 {
		case 0, 1:
			domains[i] = fmt.Sprintf("sub.ad-%d.example.com", i)  // blocked via parent
		case 2:
			domains[i] = fmt.Sprintf("cdn.tracker-%d.net", i) // blocked via parent
		case 3:
			domains[i] = fmt.Sprintf("deep.sub.malware-%d.io", i) // blocked via grandparent
		default:
			domains[i] = fmt.Sprintf("safe-%d.org", i) // clean
		}
	}

	b.ResetTimer()
	b.ReportAllocs()
	for n := 0; n < b.N; n++ {
		for _, d := range domains {
			_ = t.HasParentOf(d)
		}
	}
}

// ─── BenchmarkPGO_DNSMsg ─────────────────────────────────────────────────────

// BenchmarkPGO_DNSMsg exercises dns.Msg Pack/Unpack, which runs on every
// inbound request and outbound reply inside blocky.
func BenchmarkPGO_DNSMsg(b *testing.B) {
	type q struct {
		name  string
		qtype uint16
	}
	qs := []q{
		{"example.com.", dns.TypeA},
		{"www.github.com.", dns.TypeA},
		{"api.openai.com.", dns.TypeAAAA},
		{"ads.doubleclick.net.", dns.TypeA},
		{"tracker.example.com.", dns.TypeTXT},
		{"_dmarc.gmail.com.", dns.TypeTXT},
		{"cloudflare.com.", dns.TypeAAAA},
		{"registry.npmjs.org.", dns.TypeA},
		{"s3.amazonaws.com.", dns.TypeA},
		{"fonts.gstatic.com.", dns.TypeA},
		{"cdn.jsdelivr.net.", dns.TypeA},
		{"pagead2.googlesyndication.com.", dns.TypeA},
	}

	b.ResetTimer()
	b.ReportAllocs()
	for n := 0; n < b.N; n++ {
		for _, q := range qs {
			m := new(dns.Msg)
			m.SetQuestion(q.name, q.qtype)
			m.SetEdns0(1232, false)
			data, _ := m.Pack()
			var m2 dns.Msg
			_ = m2.Unpack(data)
		}
	}
}

// ─── BenchmarkPGO_Server ─────────────────────────────────────────────────────

// BenchmarkPGO_Server runs the full blocky production path end-to-end.
// It starts a real server on 127.0.0.1:15353 and drives it with
// pre-built DNS queries via dns.Client.
//
// Skipped when 1.1.1.1 is unreachable.
func BenchmarkPGO_Server(b *testing.B) {
	if !upstreamReachable() {
		b.Skip("1.1.1.1:53 unreachable — skipping full-stack benchmark")
	}

	const listenAddr = "127.0.0.1:15353"

	cfg := &config.Config{}

	// Upstream: Cloudflare 1.1.1.1 over UDP/TCP
	cfg.Upstreams.Groups = config.UpstreamGroups{
		"default": {
			config.Upstream{Net: config.NetProtocolTcpUdp, Host: "1.1.1.1", Port: 53},
		},
	}
	cfg.Upstreams.Timeout = config.Duration(3 * time.Second)

	// Blocking: inline deny list — no HTTP download needed at startup.
	cfg.Blocking.BlockType = "zeroIP"
	cfg.Blocking.Denylists = map[string][]config.SourceConfig{
		"ads": {
			{Inline: strings.Join([]string{
				"doubleclick.net",
				"googleadservices.com",
				"googlesyndication.com",
				"pagead2.googlesyndication.com",
				"ads.facebook.com",
				"tracking.example.com",
			}, "\n")},
		},
	}
	cfg.Blocking.ClientGroupsBlock = map[string][]string{
		"default": {"ads"},
	}

	// Caching: short minimum so we exercise both cache-miss and cache-hit paths.
	cfg.Caching.MinCachingTime = config.Duration(30 * time.Second)
	cfg.Caching.MaxCachingTime = config.Duration(5 * time.Minute)

	// Listen on a high loopback port to avoid needing CAP_NET_BIND_SERVICE.
	cfg.Ports.DNS = config.ListenConfig{listenAddr}

	// Disable noisy subsystems that add latency without PGO value.
	cfg.QueryLog.Type = config.QueryLogTypeNone
	cfg.Prometheus.Enable = false

	// ── start server ──────────────────────────────────────────────────────
	ctx, cancel := context.WithCancel(context.Background())
	b.Cleanup(cancel)

	srv, err := server.NewServer(ctx, cfg)
	if err != nil {
		b.Fatal("server.NewServer:", err)
	}

	errCh := make(chan error, 1)
	go func() { errCh <- srv.Start(ctx, errCh) }()

	// Poll until the server accepts a DNS query (up to 10 s).
	probeClient := &dns.Client{Net: "udp", Timeout: 500 * time.Millisecond}
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		m := new(dns.Msg)
		m.SetQuestion("health.check.local.", dns.TypeA)
		if _, _, err := probeClient.Exchange(m, listenAddr); err == nil {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}

	// Fail fast if the server errored during startup.
	select {
	case err := <-errCh:
		b.Fatal("server start error:", err)
	default:
	}

	// ── pre-build query messages ───────────────────────────────────────────
	type qentry struct {
		name  string
		qtype uint16
	}
	queries := []qentry{
		// Non-blocked — pass to upstream first time, then served from cache.
		{"google.com.", dns.TypeA},
		{"github.com.", dns.TypeA},
		{"cloudflare.com.", dns.TypeAAAA},
		{"en.wikipedia.org.", dns.TypeA},
		{"golang.org.", dns.TypeA},
		{"api.github.com.", dns.TypeA},
		{"bbc.co.uk.", dns.TypeA},
		{"cdn.jsdelivr.net.", dns.TypeA},
		// Blocked — blocking resolver returns 0.0.0.0 immediately (no upstream).
		{"doubleclick.net.", dns.TypeA},
		{"googleadservices.com.", dns.TypeA},
		{"sub.doubleclick.net.", dns.TypeA},
		{"tracking.example.com.", dns.TypeAAAA},
		// Misc record types.
		{"example.com.", dns.TypeTXT},
		{"_dmarc.gmail.com.", dns.TypeTXT},
		{"gmail.com.", dns.TypeMX},
		{"cloudflare.com.", dns.TypeA},
	}

	msgs := make([]*dns.Msg, len(queries))
	for i, q := range queries {
		m := new(dns.Msg)
		m.SetQuestion(q.name, q.qtype)
		m.SetEdns0(4096, false)
		msgs[i] = m
	}

	hotClient := &dns.Client{Net: "udp", Timeout: 3 * time.Second}

	b.ResetTimer()
	b.ReportAllocs()
	for n := 0; n < b.N; n++ {
		msg := msgs[n%len(msgs)]
		clone := msg.Copy() // don't reuse ID across iterations
		clone.Id = dns.Id()
		_, _, _ = hotClient.Exchange(clone, listenAddr)
	}
}
