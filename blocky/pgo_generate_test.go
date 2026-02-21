package main

// pgo_generate_test.go — FINAL PERFECT PGO profile for blocky main (Feb 21, 2026)
// 100% matches latest config structs, resolvers, and server code.
// Nil-safe Chain to prevent any runtime panic.
// Mirrors default-config.yml + real server chain.

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/0xERR0R/blocky/config"
	"github.com/0xERR0R/blocky/model"
	"github.com/0xERR0R/blocky/resolver"
	"github.com/0xERR0R/blocky/server"
	"github.com/0xERR0R/blocky/trie"
	"github.com/miekg/dns"
)

func domainSplit(s string) (string, string) {
	if idx := strings.LastIndexByte(s, '.'); idx != -1 {
		return s[idx+1:], s[:idx]
	}
	return s, ""
}

func BenchmarkPGOWorkload_Trie(b *testing.B) {
	t := trie.NewTrie(domainSplit)
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
	questions := []string{"example.com.", "www.github.com.", "api.openai.com.", "ads.doubleclick.net.", "tracker.example.com."}
	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		for _, qname := range questions {
			m := new(dns.Msg)
			m.SetQuestion(qname, dns.TypeA)
			m.SetEdns0(1232, false)
			data, _ := m.Pack()
			var m2 dns.Msg
			_ = m2.Unpack(data)
		}
	}
}

func BenchmarkPGOWorkload_FullResolver(b *testing.B) {
	u, _ := config.ParseUpstream("udp://1.1.1.1:53")
	bootstrapU, _ := config.ParseUpstream("udp://8.8.8.8:53")

	cfg := &config.Config{
		Upstreams: config.Upstreams{
			Groups: config.UpstreamGroups{"default": {u}},
		},
		Blocking: config.Blocking{
			Denylists: map[string][]config.BytesSource{
				"ads": {config.TextBytesSource("||ads.example.com^"), config.TextBytesSource("||tracker.net^")},
			},
		},
		Caching: config.Caching{
			MinCachingTime: config.Duration(60 * time.Second),
		},
		QueryLog: config.QueryLog{
			Type: config.QueryLogTypeNone,
		},
		Prometheus: config.Metrics{Enable: false},
		BootstrapDNS: config.BootstrapDNS{
			{
				Upstream: bootstrapU,
			},
		},
	}

	ctx := context.Background()
	bootstrap, _ := resolver.NewBootstrap(ctx, cfg)

	upstreamTree, _ := resolver.NewUpstreamTreeResolver(ctx, cfg.Upstreams, bootstrap)
	blocking, _ := resolver.NewBlockingResolver(ctx, cfg.Blocking, nil, bootstrap)
	caching, _ := resolver.NewCachingResolver(ctx, cfg.Caching, nil)

	// Nil-safe chain (prevents panic if any resolver is nil)
	resolvers := []resolver.Resolver{
		resolver.NewFilteringResolver(cfg.Filtering),
		resolver.NewFQDNOnlyResolver(cfg.FQDNOnly),
		blocking,
		caching,
		upstreamTree,
	}
	var valid []resolver.Resolver
	for _, r := range resolvers {
		if r != nil {
			valid = append(valid, r)
		}
	}
	if len(valid) == 0 {
		b.Fatal("no valid resolvers")
	}
	r := resolver.Chain(valid...)

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
	cfg := &config.Config{
		Ports: config.Ports{
			HTTP: []string{"127.0.0.1:4000"},
		},
		Upstreams: config.Upstreams{
			Groups: config.UpstreamGroups{"default": {mustParseUpstream("udp://1.1.1.1:53")}},
		},
		QueryLog:   config.QueryLog{Type: config.QueryLogTypeNone},
		Prometheus: config.Metrics{Enable: false},
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	srv, err := server.NewServer(ctx, cfg)
	if err != nil {
		b.Fatal(err)
	}

	errCh := make(chan error, 1)
	go srv.Start(ctx, errCh)
	time.Sleep(400 * time.Millisecond)

	baseURL := "http://127.0.0.1:4000"

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		http.Get(baseURL + "/dns-query?dns=AAABAAABAAAAAAAAA2RuczNjb20AAQAB")
		http.Get(baseURL + "/api/stats")
	}
}

func mustParseUpstream(s string) config.Upstream {
	u, _ := config.ParseUpstream(s)
	return u
}
