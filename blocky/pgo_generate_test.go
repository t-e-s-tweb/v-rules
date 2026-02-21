package main

// pgo_generate_test.go — perfect PGO profile for your current blocky (master)
// Drop in repo root next to main.go

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
	"github.com/sirupsen/logrus"
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

// mockResolver is a mock upstream resolver that doesn't require network
type mockResolver struct {
	response *model.Response
}

func (m *mockResolver) Resolve(ctx context.Context, request *model.Request) (*model.Response, error) {
	return m.response, nil
}

func (m *mockResolver) Type() string { return "MockResolver" }

func (m *mockResolver) String() string { return m.Type() }

func (m *mockResolver) IsEnabled() bool { return true }

func (m *mockResolver) LogConfig(logger *logrus.Entry) {
	logger.Info("mock resolver")
}

func BenchmarkPGOWorkload_FullResolver(b *testing.B) {
	// Use mock upstream to avoid network dependencies and bootstrap issues
	mockUpstream := &mockResolver{
		response: &model.Response{
			RType: model.ResponseTypeRESOLVED,
			Res:   new(dns.Msg),
		},
	}

	cfg := &config.Config{
		Blocking: config.Blocking{},
		Caching: config.Caching{
			MinCachingTime: config.Duration(60 * time.Second),
		},
		QueryLog: config.QueryLog{
			Type: config.QueryLogTypeNone,
		},
		Prometheus: config.Metrics{Enable: false},
	}

	ctx := context.Background()

	// Initialize resolvers that don't require bootstrap
	caching, err := resolver.NewCachingResolver(ctx, cfg.Caching, nil)
	if err != nil {
		b.Fatal("caching resolver init failed:", err)
	}

	filtering := resolver.NewFilteringResolver(cfg.Filtering)
	fqdnOnly := resolver.NewFQDNOnlyResolver(cfg.FQDNOnly)

	// Chain: filtering -> FQDN-only -> caching -> mock upstream
	// Order matters: request flows left to right, response flows right to left
	r := resolver.Chain(filtering, fqdnOnly, caching, mockUpstream)

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
			HTTP: []string{"127.0.0.1:18080"}, // Use high port to avoid conflicts
		},
		Upstreams: config.Upstreams{
			Groups: config.UpstreamGroups{"default": {mustParseUpstream("udp://1.1.1.1:53")}},
		},
		QueryLog:   config.QueryLog{Type: config.QueryLogTypeNone},
		Prometheus: config.Metrics{Enable: false},
		// Add bootstrap DNS to prevent resolver initialization issues
		BootstrapDNS: config.BootstrapDNS{
			{Upstream: mustParseUpstream("udp://1.1.1.1:53")},
		},
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

	// Verify server is ready
	if _, err := http.Get("http://127.0.0.1:18080/api/stats"); err != nil {
		b.Fatal("server not ready:", err)
	}

	b.ResetTimer()
	b.ReportAllocs()
	client := &http.Client{Timeout: 5 * time.Second}
	for i := 0; i < b.N; i++ {
		_, _ = client.Get("http://127.0.0.1:18080/dns-query?dns=AAABAAABAAAAAAAAA2RuczNjb20AAQAB")
		_, _ = client.Get("http://127.0.0.1:18080/api/stats")
	}
}

func mustParseUpstream(s string) config.Upstream {
	u, err := config.ParseUpstream(s)
	if err != nil {
		panic(err)
	}
	return u
}
