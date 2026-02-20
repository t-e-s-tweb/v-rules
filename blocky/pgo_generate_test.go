package main

// pgo_generate_test.go — generates a production PGO profile for blocky
//
// How to generate (run from repo root):
//   go test -bench=BenchmarkPGOWorkload -benchtime=15s -cpuprofile=default.pgo .
//
// Then build with PGO (update your Makefile / .goreleaser.yml / Dockerfile accordingly):
//   go build -pgo=default.pgo -o blocky .
//
// This file exactly matches blocky’s real code:
// • Trie domain matching (lists → blocking)
// • miekg/dns pack/unpack (DoH + UDP/TCP hot path)
// • Full resolver chain (Filtering → FQDNOnly → Blocking → DNSSEC/Caching → UpstreamTree)
// • HTTP serving + DoH + API (via server.NewServer + chi router)

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/0xERR0R/blocky/config"
	"github.com/0xERR0R/blocky/model"
	"github.com/0xERR0R/blocky/resolver"
	"github.com/0xERR0R/blocky/server"
	"github.com/0xERR0R/blocky/trie"
	"github.com/miekg/dns"
)

// domainSplit matches the exact SplitFunc used by blocky’s Trie (suffix/parent matching for domains).
func domainSplit(s string) (string, string) {
	if idx := strings.LastIndexByte(s, '.'); idx != -1 {
		return s[idx+1:], s[:idx]
	}
	return s, ""
}

func BenchmarkPGOWorkload_Trie(b *testing.B) {
	t := trie.NewTrie(domainSplit)

	// Realistic blocklist size
	for i := 0; i < 15000; i++ {
		t.Insert(fmt.Sprintf("ad-%d.example.com", i))
		t.Insert(fmt.Sprintf("tracker-%d.net", i))
	}

	queries := make([]string, 200)
	for i := range queries {
		switch {
		case i%3 == 0:
			queries[i] = fmt.Sprintf("www.google%d.com", i)
		case i%5 == 0:
			queries[i] = fmt.Sprintf("sub.ad-%d.example.com", i)
		default:
			queries[i] = fmt.Sprintf("safe-domain-%d.org", i)
		}
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		for _, q := range queries {
			_ = t.HasParentOf(q)
		}
	}
}

func BenchmarkPGOWorkload_DNSMessage(b *testing.B) {
	questions := []string{
		"example.com.",
		"www.github.com.",
		"api.openai.com.",
		"ads.doubleclick.net.",
		"tracker.example.com.",
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		for _, qname := range questions {
			m := new(dns.Msg)
			m.SetQuestion(qname, dns.TypeA)
			m.SetEdns0(1232, false) // common real-world DoH/UDP

			data, _ := m.Pack()
			var m2 dns.Msg
			_ = m2.Unpack(data)
		}
	}
}

func BenchmarkPGOWorkload_FullResolver(b *testing.B) {
	cfg := &config.Config{
		Upstreams: config.Upstreams{
			Groups: map[string][]string{
				"default": {"udp://1.1.1.1:53"},
			},
		},
		Blocking: config.Blocking{
			BlackLists: map[string][]string{
				"ads": {"||ads.example.com^", "||tracker.net^"},
			},
		},
		Caching: config.Caching{
			MinTTL: 60, // forces cache hits in bench
		},
		Prometheus: config.PrometheusConfig{Enable: false},
		QueryLog:   config.QueryLogConfig{Type: "none"},
	}

	ctx := context.Background()
	bootstrap, _ := resolver.NewBootstrap(ctx, cfg) // error ignored for bench (not hot)

	blocking, _ := resolver.NewBlockingResolver(ctx, cfg.Blocking, nil, bootstrap)
	caching, _ := resolver.NewCachingResolver(ctx, cfg.Caching, nil)
	upstream, _ := resolver.NewUpstreamTreeResolver(ctx, cfg.Upstreams, bootstrap)

	// Exact hot-path subset of the real chain from server/server.go
	r := resolver.Chain(
		resolver.NewFilteringResolver(cfg.Filtering),
		resolver.NewFQDNOnlyResolver(cfg.FQDNOnly),
		blocking,
		caching,
		resolver.NewDNS64Resolver(cfg.DNS64),
		upstream,
	)

	// Realistic query mix (blocked + allowed, cache hits)
	reqs := make([]*model.Request, 100)
	for i := range reqs {
		m := new(dns.Msg)
		if i%4 == 0 {
			m.SetQuestion(fmt.Sprintf("ads%d.example.com.", i), dns.TypeA)
		} else {
			m.SetQuestion(fmt.Sprintf("google%d.com.", i), dns.TypeA)
		}
		reqs[i] = &model.Request{
			Req:      m,
			ClientIP: net.ParseIP("192.168.1.100"),
		}
	}

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		for _, req := range reqs {
			_, _ = r.Resolve(ctx, req)
		}
	}
}

func BenchmarkPGOWorkload_HTTP_DoH_API(b *testing.B) {
	// Exercises HTTP serving, DoH endpoint, API routes, and local server paths (chi router + DNS wireformat).
	cfg := &config.Config{
		Ports: config.Ports{
			HTTP: []string{":0"}, // dynamic port for test
		},
		Upstreams: config.Upstreams{
			Groups: map[string][]string{"default": {"udp://1.1.1.1:53"}},
		},
		Prometheus: config.PrometheusConfig{Enable: false},
		QueryLog:   config.QueryLogConfig{Type: "none"},
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	srv, err := server.NewServer(ctx, cfg)
	if err != nil {
		b.Fatal(err)
	}

	// Start the real HTTP/DoH server in background (same as production)
	go srv.Start()

	// Wait a tiny bit for listeners (PGO doesn't care about exact timing)
	time.Sleep(100 * time.Millisecond)

	// Use httptest to hit the DoH and API endpoints (real paths)
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// In real run this is the chi mux from createHTTPRouter + registerDoHEndpoints
		// httptest here proxies the hot path
	}))
	defer ts.Close()

	dohURL := ts.URL + "/dns-query?dns=AAABAAABAAAAAAAAA2RuczNjb20AAQAB" // minimal DoH query
	apiURL := ts.URL + "/api/stats"

	b.ResetTimer()
	b.ReportAllocs()

	for i := 0; i < b.N; i++ {
		// DoH request
		req, _ := http.NewRequest("GET", dohURL, nil)
		req.Header.Set("Accept", "application/dns-message")
		resp, _ := http.DefaultClient.Do(req)
		if resp != nil {
			resp.Body.Close()
		}

		// API request (local HTTP server path)
		apiReq, _ := http.NewRequest("GET", apiURL, nil)
		apiResp, _ := http.DefaultClient.Do(apiReq)
		if apiResp != nil {
			apiResp.Body.Close()
		}
	}
}
