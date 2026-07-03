# Morita Bot Source Seal Operations

Use these commands only with local existing artifacts:

```powershell
python scripts/build_morita_bot_source_seal_v1.py --inspect-candidates
python scripts/build_morita_bot_source_seal_v1.py --validate-candidate <candidate_id_or_path>
python scripts/build_morita_bot_source_seal_v1.py --build-source-artifact --spec-id morita_bot_source_seal_v1 --candidate <exact_candidate_id_or_path> --output-dir market_bomb_history/morita_bot_source_seal_v1/source_artifacts/<artifact_id>
python scripts/build_morita_bot_source_seal_v1.py --verify-source-artifact --artifact-dir market_bomb_history/morita_bot_source_seal_v1/source_artifacts/<artifact_id>
```

Do not use network access, provider APIs, current scanner downloads, aggregate-only reports, or revised Bot logic. If code/config/input lineage, timing, or core outcomes are ambiguous, stop with a blocked status.
