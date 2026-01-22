# Task: Implement Caching Layer

## Description

Add Redis-based caching to improve API response times for read-heavy endpoints.

## Requirements

- [ ] Cache GET responses with configurable TTL per endpoint
- [ ] Invalidate cache on POST/PUT/DELETE operations
- [ ] Add cache-control headers to responses
- [ ] Implement cache warming on application startup
- [ ] Add cache hit/miss metrics

## Success Criteria

- All existing tests pass
- New cache tests pass with >80% coverage
- Response time < 50ms for cached endpoints
- Cache hit rate > 80% for read endpoints

## Technical Notes

- Use existing Redis connection from `config/redis.ts`
- Follow caching patterns in `src/cache/base.ts`
- Implement cache key generation following `docs/ai-context/conventions.md`

## Out of Scope

- Cache clustering/sharding
- Cache persistence across restarts
- GraphQL caching

Output `<promise>COMPLETE</promise>` when all requirements are met.
