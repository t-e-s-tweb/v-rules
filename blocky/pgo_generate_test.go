// pgo_generate_test.go — PGO workload benchmarks for 0xERR0R/blocky
//
// Drop this file in the repo root (next to main.go) and run:
//
//	go test -run='^$' -bench=. -benchtime=30s -cpuprofile=default.pgo .
//	go build -pgo=default.pgo .
//
// Offline-only (no upstream DNS):
//
//	go test -run='^$' -bench='^BenchmarkPGO_(Trie|DNSMsg)$' -benchtime=30s -cpuprofile=default.pgo .

package main

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/0xERR0R/blocky/config"
	"github.com/0xERR0R/blocky/server"
	"github.com/0xERR0R/blocky/trie"
	"github.com/miekg/dns"
)

func splitDomain(s string) (string, string) {
	if i := strings.LastIndexByte(s, '.'); i >= 0 {
		return s[i+1:], s[:i]
	}
	return s, ""
}

func upstreamReachable() bool {
	cl := &dns.Client{Net: "udp", Timeout: 2 * time.Second}
	m := new(dns.Msg)
	m.SetQuestion("a.root-servers.net.", dns.TypeA)
	_, _, err := cl.Exchange(m, "1.1.1.1:53")
	return err == nil
}

// ─── BenchmarkPGO_Trie ───────────────────────────────────────────────────────

func BenchmarkPGO_Trie(b *testing.B) {
	t := trie.NewTrie(splitDomain)
	for i := 0; i < 15_000; i++ {
		t.Insert(fmt.Sprintf("ad-%d.example.com", i))
		t.Insert(fmt.Sprintf("tracker-%d.net", i))
		t.Insert(fmt.Sprintf("malware-%d.io", i))
	}
	domains := make([]string, 500)
	for i := range domains {
		switch i % 10 {
		case 0, 1:
			domains[i] = fmt.Sprintf("sub.ad-%d.example.com", i)
		case 2:
			domains[i] = fmt.Sprintf("cdn.tracker-%d.net", i)
		case 3:
			domains[i] = fmt.Sprintf("deep.sub.malware-%d.io", i)
		default:
			domains[i] = fmt.Sprintf("safe-%d.org", i)
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

func BenchmarkPGO_Server(b *testing.B) {
	if !upstreamReachable() {
		b.Skip("1.1.1.1:53 unreachable — skipping full-stack benchmark")
	}

	const listenAddr = "127.0.0.1:15353"

	inlineList := strings.Join([]string{
		"doubleclick.net",
		"googleadservices.com",
		"googlesyndication.com",
		"pagead2.googlesyndication.com",
		"ads.facebook.com",
		"tracking.example.com",
	}, "\n")

	cfg := &config.Config{}

	cfg.Upstreams.Groups = config.UpstreamGroups{
		"default": {
			config.Upstream{Net: config.NetProtocolTcpUdp, Host: "1.1.1.1", Port: 53},
		},
	}
	cfg.Upstreams.Timeout = config.Duration(3 * time.Second)

	cfg.Blocking.BlockType = "zeroIP"
	cfg.Blocking.Denylists = map[string][]config.BytesSource{
		"ads": {config.BytesSource(inlineList)},
	}
	cfg.Blocking.ClientGroupsBlock = map[string][]string{
		"default": {"ads"},
	}

	cfg.Caching.MinCachingTime = config.Duration(30 * time.Second)
	cfg.Caching.MaxCachingTime = config.Duration(5 * time.Minute)

	cfg.Ports.DNS = config.ListenConfig{listenAddr}

	cfg.QueryLog.Type = config.QueryLogTypeNone
	cfg.Prometheus.Enable = false

	ctx, cancel := context.WithCancel(context.Background())
	b.Cleanup(cancel)

	srv, err := server.NewServer(ctx, cfg)
	if err != nil {
		b.Fatal("server.NewServer:", err)
	}

	errCh := make(chan error, 1)
	go srv.Start(ctx, errCh)

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

	select {
	case err := <-errCh:
		b.Fatal("server start error:", err)
	default:
	}

	type qentry struct {
		name  string
		qtype uint16
	}
	queries := []qentry{
		{"google.com.", dns.TypeA},
		{"github.com.", dns.TypeA},
		{"cloudflare.com.", dns.TypeAAAA},
		{"en.wikipedia.org.", dns.TypeA},
		{"golang.org.", dns.TypeA},
		{"api.github.com.", dns.TypeA},
		{"bbc.co.uk.", dns.TypeA},
		{"cdn.jsdelivr.net.", dns.TypeA},
		{"doubleclick.net.", dns.TypeA},
		{"googleadservices.com.", dns.TypeA},
		{"sub.doubleclick.net.", dns.TypeA},
		{"tracking.example.com.", dns.TypeAAAA},
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
		clone := msg.Copy()
		clone.Id = dns.Id()
		_, _, _ = hotClient.Exchange(clone, listenAddr)
	}
}
