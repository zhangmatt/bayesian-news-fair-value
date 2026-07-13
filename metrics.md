# Metrics Report

The posterior has a higher Brier score than the market in this run.
The posterior-minus-market Brier delta is +0.002417 with a paired bootstrap 95% CI [-0.000348, +0.007153], so the difference is within noise for n=50.
The blend-minus-market Brier delta is +0.000962 with 95% CI [-0.000359, +0.003148], so the blend difference is within noise.

| Metric | Value |
| --- | ---: |
| Events analyzed | 50 |
| News items processed | 448 |
| Brier, market | 0.005970 |
| Brier, posterior | 0.008387 |
| Brier, 50/50 blend | 0.006932 |
| Calibration error | 0.034205 |
| Divergence hit-rate | 0.000000 |
| Flagged divergences | 8 |
| YES stances | 47 |
| NO stances | 5 |
| Neutral stances | 396 |
| Posterior-market delta | +0.002417 |
| Posterior-market 95% CI low | -0.000348 |
| Posterior-market 95% CI high | +0.007153 |
| Blend-market delta | +0.000962 |
| Blend-market 95% CI low | -0.000359 |
| Blend-market 95% CI high | +0.003148 |

## Corpus

- Source: Polymarket Gamma + Polymarket CLOB prices-history + Google News RSS
- Built at: 2026-07-10T09:31:17.328680Z
- Market forecast snapshot: 1 days before close, using the latest CLOB history point at or before that time.
- News window: 30 days before the market as-of timestamp.
- News source requested: `google_rss`
- Wikipedia fallback allowed: `False`
- No-lookahead rule: GDELT uses seendate as first-seen point-in-time; Google News RSS fallback uses article pubDate as the observed timestamp and filters pubDate <= market as_of
- Disabled hosts during run: `[]`
- Skipped candidates: `{'excluded_tag': 5, 'no_news': 3, 'source:google_rss': 50}`

## Event Replay

| Event | Outcome | Market | Posterior | Blend | Gap | Flagged | News |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| polymarket:0xdd22472e552920b8438158ea7238bfadfa4f736aa4cee91a6b86c39ead110917 | 1 | 0.628 | 0.654 | 0.641 | 0.026 | False | 12 |
| polymarket:0x14018049e265a2d88f284be9588e2e3542e3a3df08ccdb344d28355dd7fdd8ef | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0xced9f9d90c94db9f1e1dbd7d9fba82fe4fa7431c0d4e91e28896c8ac2d6acadd | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 4 |
| polymarket:0x40bbdd26dc08406eedcb913efee7f7faddf50e16fc21caedb4972d57fd71e0d1 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 5 |
| polymarket:0x7da35195ac3c7bf167f88ab0c27067a99020e36de67d39968b71d9debcdd925e | 0 | 0.001 | 0.049 | 0.025 | 0.048 | False | 6 |
| polymarket:0xad6d309aaa500d96855996e84da00dfb2379548a693ca684d0877cf94fec05d1 | 0 | 0.001 | 0.000 | 0.000 | -0.000 | False | 4 |
| polymarket:0x696baf880832d000a37ea87cc94235b1ac58e7e9fe7a144ccf5d141877629134 | 0 | 0.001 | 0.004 | 0.002 | 0.004 | False | 3 |
| polymarket:0xc6485bb7ea46d7bb89beb9c91e7572ecfc72a6273789496f78bc5e989e4d1638 | 0 | 0.392 | 0.507 | 0.449 | 0.115 | True | 12 |
| polymarket:0x230144e34a84dfd0ebdc6de7fde37780e28154f6f84dd8880c7f0e58d302d448 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0x63634b4e14297a748923f86dca4fa0c6c659db0f5fadeeb8e419e48e20759c34 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0xf6106065ec5d5dae7eca350be64e5246ae331b35937ea55b64152f65fbc0b37f | 0 | 0.001 | 0.004 | 0.002 | 0.003 | False | 2 |
| polymarket:0x3120827dc12167d09fd9f08233e2b540054a2ed90aad65c023bc1da9d38b29d9 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 0 |
| polymarket:0x08f5fe8d0d29c08a96f0bc3dfb52f50e0caf470d94d133d95d38fa6c847e0925 | 0 | 0.001 | 0.040 | 0.020 | 0.039 | False | 6 |
| polymarket:0xd1cce1f51effdf3957144fdc87b5e8aace1d1f7ab21976a046b71744ecad8443 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 4 |
| polymarket:0xb92f22143e7b48609a82573fa8197dc73683a15acb467b0f51ee63da7e3f520b | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 7 |
| polymarket:0x55c551896c10a74861f2fd88b4f928694310114704cc74b29b9760d1156cade6 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 7 |
| polymarket:0x73ac4c1e5be0a89685328c9f5b833d828ffd62dfa07ceaf8536edbc43aa5f51e | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 0 |
| polymarket:0x17815081230e3b9c78b098162c33b1ffa68c4ec29c123d3d14989599e0c2e113 | 0 | 0.001 | 0.019 | 0.010 | 0.018 | False | 12 |
| polymarket:0x35cc41270f5cdfd59b45e68ab85dc51b0b900d286a6c74ea006b8572d9ff5934 | 0 | 0.004 | 0.022 | 0.013 | 0.018 | False | 12 |
| polymarket:0xe93c89c41d1bb08d3bb40066d8565df301a696563b2542256e6e8bbbb1ec490d | 1 | 0.995 | 0.995 | 0.995 | 0.000 | False | 12 |
| polymarket:0x7c6c69d91b21cbbea08a13d0ad51c0e96a956045aaadc77bce507c6b0475b66e | 0 | 0.001 | 0.019 | 0.010 | 0.018 | False | 12 |
| polymarket:0xcd1b6b71a1964f15e2c14809594cbfa0d576270e8ef94c8c24913121097e09e5 | 1 | 0.997 | 0.997 | 0.997 | 0.001 | False | 12 |
| polymarket:0xb26fd99a7b7bae4e13c9bb3becf65353708a805f9c1aea74484d107e6ba512cd | 0 | 0.001 | 0.074 | 0.037 | 0.073 | True | 12 |
| polymarket:0x0c12d7b5322f432a0c4ac8806b476c7483c4d44061ca1188b6f749ec9db34996 | 0 | 0.001 | 0.060 | 0.030 | 0.060 | True | 5 |
| polymarket:0x4eb8e44c37e307a2125f400b675e98861d091f9e50f5be07a25304c930cf85aa | 0 | 0.001 | 0.002 | 0.001 | 0.001 | False | 4 |
| polymarket:0x534da3946b8da84a8687e346e735fcc1d7c7078c057b1a7769cb9991b3e67968 | 0 | 0.001 | 0.034 | 0.017 | 0.033 | False | 12 |
| polymarket:0xf488aacaba74914fe181c68d8b6195e13c4ec8b6c1b215c299d297666297200e | 0 | 0.001 | 0.054 | 0.027 | 0.053 | True | 12 |
| polymarket:0xf75076205d589c02ac13263b0d59041563695a7518d65134f8eb8c61dda22262 | 0 | 0.001 | 0.001 | 0.001 | 0.001 | False | 3 |
| polymarket:0xf3a7a2365b6ec113117184bb2d1b020577355a1028fde0b32671c4cfbbbbd589 | 0 | 0.001 | 0.028 | 0.014 | 0.028 | False | 12 |
| polymarket:0xb80a8a4ecb9344bfe81bb620638fa2882b5f57663bbe268c4bb2b97ece7717b9 | 0 | 0.001 | 0.035 | 0.018 | 0.035 | False | 11 |
| polymarket:0x21dacbae08cd922e9fe1e5f3a4b2ea09820d36f2ed368d6b53683b0fc1f16fe1 | 0 | 0.001 | 0.055 | 0.028 | 0.055 | True | 7 |
| polymarket:0x6d617a838210e0710a2a946814d1f26ed6bd3ffb76d0ef49959e0d2f75556944 | 0 | 0.001 | 0.028 | 0.014 | 0.028 | False | 4 |
| polymarket:0x37658cacdccbb4d2d6dd4cae8cfd43b268e695aab51973a70be339f1b90d9a94 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 0 |
| polymarket:0x198d833c085ed0c858165192e9fd446c5392dbcdedd1132d89c578c0b5c29b2f | 0 | 0.001 | 0.059 | 0.030 | 0.058 | True | 12 |
| polymarket:0x34b8fa269775d034f3d98b6848e0a7c5212efcaa0c98e6f8fb54c5d6f72b3705 | 0 | 0.001 | 0.059 | 0.030 | 0.058 | True | 12 |
| polymarket:0x215625b9e962f3f499f832c77dd4caa400bd8435369b5fd65e8673c8b2c4da66 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0x037c9d29c04a2f6a5373ae7db7779cb40a751ca372de1e55999397a8f571c67e | 0 | 0.001 | 0.000 | 0.000 | -0.000 | False | 6 |
| polymarket:0x265366ede72d73e137b2b9095a6cdc9be6149290caa295738a95e3d881ad0865 | 0 | 0.003 | 0.074 | 0.038 | 0.072 | True | 12 |
| polymarket:0x61b66d02793b4a68ab0cc25be60d65f517fe18c7d654041281bb130341244fcc | 1 | 0.933 | 0.933 | 0.933 | 0.000 | False | 12 |
| polymarket:0xdcc87b9ca36015e396bd0eebca29e854a136ed2b0b701049d1ee9da6bee3eb35 | 0 | 0.003 | 0.003 | 0.003 | 0.000 | False | 12 |
| polymarket:0x705371444684d676041d1010a94cae3a657340fa4809b4307de3c173a35e0957 | 0 | 0.003 | 0.002 | 0.002 | -0.000 | False | 12 |
| polymarket:0xc82669901de7cb0be25c1d8de39fbbe8e2ddc0aacba0a30a663ed13c3b9eb06d | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0x46d40e851b24d9b0af4bc1942ccd86439cae82a9011767da14950df0ad997adf | 0 | 0.043 | 0.043 | 0.043 | 0.000 | False | 12 |
| polymarket:0x998acf9ed1bbda06d59df70786441468872c72b2de59cacbea93625b14a5efcb | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0xcba397f49b319dccb5f1b92c3710518d1c4f8f1dee86577b4bb243f3ca77e389 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0xe844e12246d8504b8ec30c1d461718dbc9645fb73487ca50e5e716eefbb2bc63 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0x22d3d4722ce79dae5b2594df2ce89b1c283e3227b78718353bcca2e854d115a4 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0x60acc46cda1f0619259acf3ef8c77bf734ff08cbed256ca3d1e9444138e21266 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0xfee4b6988b9513dab72118c97abeb4369f0d9a7c2290337ca5d5c2f116a148c2 | 0 | 0.001 | 0.000 | 0.001 | -0.000 | False | 12 |
| polymarket:0x94947a23e965124fa382e3ff89827b7bb00c2e2f3f9c0b92137e639d4cbfb080 | 0 | 0.005 | 0.005 | 0.005 | 0.000 | False | 12 |

Interpretation: this replay uses date-bounded Google News RSS headlines/snippets. That is a genuine news corpus, but pubDate is weaker than GDELT's first-seen timestamp.
Treat the bootstrap interval as a noise check, not a full inference procedure for market dependence or parameter selection.
