# Platform Media Execution

Depends on: approved shared input contract. Operational sequence follows settings, but no paid/model client dependency. Status: planning.

1. Read parent media audit plus browser/auth/product-search/submodule specs. Reconfirm fork revision/dirty state; preserve every pre-existing edit.
2. Implement protocol, request matching, safe temp-handle transfer and backend validation with synthetic assets first. Keep browser/profile access out of tests.
3. Implement one platform at a time: Toutiao, Weibo, Kuaishou, Douyin, Xiaohongshu. Follow each audit row's narrow exact-ID path and gaps; no generic crawler fallback.
4. Add focused fork tests under `third_party/MediaCrawler/tests/test_product_media_*.py` and backend boundary tests under `backend/tests/test_content_enrichment.py` (proposed new names). Include malicious input, manual-action, ownership, limit and media-absence matrices.
5. Sync source only to Centaurus; run new explicit media test paths in the fork's isolated uv environment plus its existing product search/auth protocol tests. Discover exact existing paths with `rg --files third_party/MediaCrawler/tests` before constructing the command; do not invoke live generic crawling. Run parent backend frozen gates.
6. Obtain explicit user readiness for local-browser live acceptance. Test one bounded stored source per supported platform/modality, record only sanitized outcomes/counts and stop on challenges. Do not mistake fixture success for live support.
7. Required Trellis check must verify both fork/backend sides and unchanged search/login/open routes. When publishing is separately requested, push the fork commit first, validate reachability, then update the parent gitlink; follow submodule reproducibility gate.

Risk points: persistent worker protocol, backend decoder, ownership coordinator, media URL/download safety and submodule gitlink. Rollback disables the new command without deleting data or touching browser profiles. If a platform requires a broader mechanism than approved, return to planning rather than silently adding it.
