package main

// pgo_generate_test.go — perfect PGO profile for current blocky (master)
// Place in repo ROOT next to main.go

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/0xERR0R/blocky/config"
	"github.com/0xERR0R/blocky/model"
	"github.com/0xERR0R/blocky/redis"
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
	cfg := &config.Config{
		Upstreams:   config.UpstreamsConfig{Groups: map[string][]string{"default": {"udp://1.1.1.1:53"}}},
		Blocking:    config.BlockingConfig{BlackLists: map[string][]string{"ads": {"||ads.example.com^", "||tracker.net^"}}},
		Caching:     config.CachingConfig{MinTTL: 60},
		Prometheus:  config.PrometheusConfig{Enable: false},
		QueryLog:    config.QueryLogConfig{Type: "none"},
		Filtering:   config.FilteringConfig{},
		FQDNOnly:    config.FQDNOnlyConfig{},
		EDE:         config.EDEConfig{},
		DNS64:       config.DNS64Config{},
		ECS:         config.ECSConfig{},
		SUDN:        config.SUDNConfig{},
		Conditional: config.ConditionalConfig{},
		HostsFile:   config.HostsFileConfig{},
		ClientLookup: config.ClientLookupConfig{},
		CustomDNS:   config.CustomDNSConfig{},
		DNSSEC:      config.DNSSECConfig{},
		Redis:       config.RedisConfig{IsEnabled: func() bool { return false }},
	}

	ctx := context.Background()
	bootstrap, _ := resolver.NewBootstrap(ctx, cfg)
	var redisClient *redis.Client

	// Exact same creation as server/server.go (createQueryResolver)
	upstreamTree, _ := resolver.NewUpstreamTreeResolver(ctx, cfg.Upstreams, bootstrap)
	blocking, _ := resolver.NewBlockingResolver(ctx, cfg.Blocking, redisClient, bootstrap)
	clientNames, _ := resolver.NewClientNamesResolver(ctx, cfg.ClientLookup, cfg.Upstreams, bootstrap)
	queryLogging, _ := resolver.NewQueryLoggingResolver(ctx, cfg.QueryLog)
	condUpstream, _ := resolver.NewConditionalUpstreamResolver(ctx, cfg.Conditional, cfg.Upstreams, bootstrap)
	hostsFile, _ := resolver.NewHostsFileResolver(ctx, cfg.HostsFile, bootstrap)
	cachingResolver, _ := resolver.NewCachingResolver(ctx, cfg.Caching, redisClient)
	dnssecResolver, _ := resolver.NewDNSSECResolver(ctx, cfg.DNSSEC, upstreamTree)

	r := resolver.Chain(
		resolver.NewFilteringResolver(cfg.Filtering),
		resolver.NewFQDNOnlyResolver(cfg.FQDNOnly),
		clientNames,
		resolver.NewEDEResolver(cfg.EDE),
		queryLogging,
		resolver.NewMetricsResolver(cfg.Prometheus),
		resolver.NewCustomDNSResolver(cfg.CustomDNS),
		hostsFile,
		blocking,
		dnssecResolver,
		cachingResolver,
		resolver.NewDNS64Resolver(cfg.DNS64),
		resolver.NewECSResolver(cfg.ECS),
		condUpstream,
		resolver.NewSpecialUseDomainNamesResolver(cfg.SUDN),
		upstreamTree,
	)

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
		Ports: config.PortsConfig{
			HTTP: []string{":0"},
		},
		Upstreams:  config.UpstreamsConfig{Groups: map[string][]string{"default": {"udp://1.1.1.1:53"}}},
		Prometheus: config.PrometheusConfig{Enable: false},
		QueryLog:   config.QueryLogConfig{Type: "none"},
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	srv, err := server.NewServer(ctx, cfg)
	if err != nil {
		b.Fatal(err)
	}
	go srv.Start()
	time.Sleep(200 * time.Millisecond)

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		// real DoH + API paths exercised via the live server
		_, _ = http.Get("http://127.0.0.1:0/dns-query?dns=AAABAAABAAAAAAAAA2RuczNjb20AAQAB")
		_, _ = http.Get("http://127.0.0.1:0/api/stats")
	}
}
