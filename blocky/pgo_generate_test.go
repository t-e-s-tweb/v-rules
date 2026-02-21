package main

// pgo_generate_test.go — improved PGO profile for blocky
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

// realisticResolver simulates a real upstream without network calls
// It processes the request and returns a realistic response
type realisticResolver struct {
	typed    string
	response *model.Response
}

func (r *realisticResolver) Resolve(ctx context.Context, request *model.Request) (*model.Response, error) {
	// Simulate some processing work (like a real resolver would do)
	resp := new(dns.Msg)
	resp.SetReply(request.Req)
	
	// Add a realistic A record response
	if len(request.Req.Question) > 0 {
		q := request.Req.Question[0]
		if q.Qtype == dns.TypeA {
			rr := &dns.A{
				Hdr: dns.RR_Header{
					Name:   q.Name,
					Rrtype: dns.TypeA,
					Class:  dns.ClassINET,
					Ttl:    300,
				},
				A: net.ParseIP("1.1.1.1"),
			}
			resp.Answer = append(resp.Answer, rr)
		}
	}
	
	return &model.Response{
		RType: model.ResponseTypeRESOLVED,
		Res:   resp,
		Reason: "resolved by realistic resolver",
	}, nil
}

func (r *realisticResolver) Type() string { return r.typed }
func (r *realisticResolver) String() string { return r.Type() }
func (r *realisticResolver) IsEnabled() bool { return true }
func (r *realisticResolver) LogConfig(logger *logrus.Entry) {
	logger.Infof("%s resolver enabled", r.typed)
}

func BenchmarkPGOWorkload_FullResolver(b *testing.B) {
	// Create a realistic resolver that actually processes DNS messages
	realisticUpstream := &realisticResolver{
		typed:    "RealisticUpstream",
		response: nil, // computed dynamically in Resolve
	}

	cfg := &config.Config{
		Blocking: config.Blocking{
			BlockType: "zeroIP",
			// Add some block lists to exercise blocking logic
			BlockLists: map[string][]string{
				"ads": {"ads.example.com", "doubleclick.net"},
			},
			ClientGroupsBlock: map[string][]string{
				"default": {"ads"},
			},
		},
		Caching: config.Caching{
			MinCachingTime: config.Duration(60 * time.Second),
			MaxCachingTime: config.Duration(60 * time.Minute),
		},
		QueryLog: config.QueryLog{
			Type: config.QueryLogTypeNone,
		},
		Prometheus: config.Metrics{Enable: false},
	}

	ctx := context.Background()

	// Initialize resolvers
	caching, err := resolver.NewCachingResolver(ctx, cfg.Caching, nil)
	if err != nil {
		b.Fatal("caching resolver init failed:", err)
	}

	// Create blocking resolver with the realistic upstream as next
	blocking, err := resolver.NewBlockingResolver(ctx, cfg.Blocking, nil, nil)
	if err != nil {
		b.Fatal("blocking resolver init failed:", err)
	}

	filtering := resolver.NewFilteringResolver(cfg.Filtering)
	fqdnOnly := resolver.NewFQDNOnlyResolver(cfg.FQDNOnly)

	// Chain: filtering -> FQDN-only -> blocking -> caching -> realistic upstream
	r := resolver.Chain(filtering, fqdnOnly, blocking, caching, realisticUpstream)

	// Mixed query types to exercise different code paths
	reqs := make([]*model.Request, 100)
	for i := range reqs {
		m := new(dns.Msg)
		switch i % 5 {
		case 0:
			// Should be blocked
			m.SetQuestion(fmt.Sprintf("ads%d.example.com.", i), dns.TypeA)
		case 1:
			// Should be blocked (doubleclick pattern)
			m.SetQuestion(fmt.Sprintf("tracker%d.doubleclick.net.", i), dns.TypeA)
		case 2:
			// AAAA query (IPv6)
			m.SetQuestion(fmt.Sprintf("google%d.com.", i), dns.TypeAAAA)
		case 3:
			// TXT query
			m.SetQuestion(fmt.Sprintf("txt%d.example.com.", i), dns.TypeTXT)
		default:
			// Normal A query
			m.SetQuestion(fmt.Sprintf("safe-domain%d.org.", i), dns.TypeA)
		}
		
		reqs[i] = &model.Request{
			Req:         m,
			ClientIP:    net.ParseIP("192.168.1.100"),
			ClientNames: []string{"test-client"},
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

// BenchmarkPGOWorkload_HTTP_API benchmarks the HTTP API without needing upstream DNS
// This is useful for profiling the HTTP layer specifically
func BenchmarkPGOWorkload_HTTP_API(b *testing.B) {
	cfg := &config.Config{
		Ports: config.Ports{
			HTTP: []string{"127.0.0.1:18080"},
		},
		// Minimal config - just enough to start HTTP server
		Upstreams: config.Upstreams{
			Groups: config.UpstreamGroups{}, // Empty
		},
		QueryLog:   config.QueryLog{Type: config.QueryLogTypeNone},
		Prometheus: config.Metrics{Enable: false},
		Blocking:   config.Blocking{BlockType: "zeroIP"},
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	srv, err := server.NewServer(ctx, cfg)
	if err != nil {
		b.Fatal(err)
	}

	errCh := make(chan error, 1)
	go srv.Start(ctx, errCh)
	time.Sleep(200 * time.Millisecond)

	// Verify server is ready
	resp, err := http.Get("http://127.0.0.1:18080/api/stats")
	if err != nil {
		b.Fatal("server not ready:", err)
	}
	resp.Body.Close()

	b.ResetTimer()
	b.ReportAllocs()
	client := &http.Client{Timeout: 5 * time.Second}
	
	// Only benchmark the API endpoint (not DoH which requires upstream)
	for i := 0; i < b.N; i++ {
		resp, _ := client.Get("http://127.0.0.1:18080/api/stats")
		if resp != nil && resp.Body != nil {
			resp.Body.Close()
		}
	}
}

// BenchmarkPGOWorkload_DNSResolution simulates the full DNS resolution pipeline
// without network by using the realistic resolver chain
func BenchmarkPGOWorkload_DNSResolution(b *testing.B) {
	// Same setup as FullResolver but focused on DNS message processing
	realisticUpstream := &realisticResolver{
		typed: "DNSUpstream",
	}

	cfg := &config.Config{
		Blocking: config.Blocking{
			BlockType: "zeroIP",
			BlockLists: map[string][]string{
				"ads": {"ads.example.com"},
			},
			ClientGroupsBlock: map[string][]string{
				"default": {"ads"},
			},
		},
		Caching: config.Caching{
			MinCachingTime: config.Duration(60 * time.Second),
		},
		QueryLog:   config.QueryLog{Type: config.QueryLogTypeNone},
		Prometheus: config.Metrics{Enable: false},
	}

	ctx := context.Background()

	caching, _ := resolver.NewCachingResolver(ctx, cfg.Caching, nil)
	blocking, _ := resolver.NewBlockingResolver(ctx, cfg.Blocking, nil, nil)
	filtering := resolver.NewFilteringResolver(cfg.Filtering)

	r := resolver.Chain(filtering, blocking, caching, realisticUpstream)

	// Pre-create diverse DNS queries
	queries := []*model.Request{}
	for i := 0; i < 50; i++ {
		m := new(dns.Msg)
		switch i % 4 {
		case 0:
			m.SetQuestion(fmt.Sprintf("ads%d.example.com.", i), dns.TypeA)
		case 1:
			m.SetQuestion(fmt.Sprintf("google%d.com.", i), dns.TypeA)
		case 2:
			m.SetQuestion(fmt.Sprintf("api%d.github.com.", i), dns.TypeAAAA)
		default:
			m.SetQuestion(fmt.Sprintf("cdn%d.cloudflare.com.", i), dns.TypeCNAME)
		}
		queries = append(queries, &model.Request{
			Req:      m,
			ClientIP: net.ParseIP("10.0.0.1"),
		})
	}

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		for _, req := range queries {
			_, _ = r.Resolve(ctx, req)
		}
	}
}
