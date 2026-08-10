# ARC-AGI-3 public harness comparison

Updated August 9, 2026.

The table includes every public harness result found during this review. It uses one best row per harness.

## Results

| Harness | Date | Model | Best public result | Cost used | Cost basis | Run and coverage |
|---|---:|---|---:|---:|---|---|
| [Tycho][tycho-code] | 2026-07-29 | Claude Opus 5 | [100.00% RHAE][tycho-scorecard] | $2,986.04 | API-equivalent estimate | One full 25-game run |
| [Retrodict][retrodict-code] | 2026-07-19 | GPT-5.6 Sol, max | [99.86% mean RHAE][retrodict-scorecard] | [$654.34][retrodict-costs] | API list prices | One full 25-game run; all 183 levels solved |
| [Schema][schema-page] | 2026-07-16 | Claude Opus 4.8 with Fable 5 fallback | [98.98% RHAE][schema-page] | At least $6,447 | Retained runs only | Fixed conditional reruns; higher per-game result retained |
| [baseline1][baseline1-code] | 2026-07-15 | GPT-5.6 Sol, xhigh | [98.97% RHAE][baseline1-scorecard] | [$2,722][retrodict-readme] | API list prices | One full 25-game run |
| [PRO-LONG][prolong-code] | 2026-07-22 | Fable 5 | [97.4% best@2][prolong-paper] | $1,750 | Paper total | Selective second runs; several games ran once |
| [Prime Agent][prime-code] | 2026-08-05 | Claude Opus 5 | [95.5% RHAE][prime-article] | [Approximately $944][prime-cost-chart] | Interpolated official chart | Three full runs; [median-run scorecard][prime-median-scorecard] public |
| [NOOA][nooa-code] | 2026-07-09 | GPT-5.6 Sol, xhigh | [85.13% RHAE][nooa-scorecard] | $332 | Paper estimate | One 25-game fleet under a two-hour cap |
| [OPINE-World][opine-code] | 2026-07-01 | Claude Opus 4.8, high | [78.37% RHAE][opine-scorecard] | $1,040 | Submitted cost | One full 25-game run |
| [Vision - Continual Learning v1][vision-code] | 2026-05-18 | Vision-CLv1 | [63.15% RHAE][vision-scorecard] | $4,788 | Submitted cost | Full public scorecard |
| [Read-Grep-Bash Agent][rgb-code] | 2026-03-13 | Claude Opus 4.6 | [50.2% RHAE][rgb-scorecard] | — | Not shown | Current scorecard exposes one game |
| [TELL][tell-code] | 2026-04-09 | Claude Opus 4.6 | [43.90% RHAE][tell-scorecard] | $1,406 | Submitted cost | Full public scorecard |
| [DreamTeam][dream-code] | 2026-05-04 | Claude Opus 4.6 and GPT-5.5 | [38.06% RHAE][dream-scorecard] | $18,000 | Submitted cost | Released full-set run; paper reports a 38.4% two-run mean |
| [Arcgentica][arcgentica-code] | 2026-03-25 | Claude Opus 4.6, high | [36.08% RHAE][arcgentica-post] | $1,005 | Author-reported cost | Full 25-game launch result under the earlier 182-level release |
| [AERA][aera-code] | 2026-05-25 | Qwen2.5-0.5B | [21.16% RHAE][aera-paper] | — | Not published | Full 25-game paper result; evaluator behavior limits comparison |
| [Continual Harness][continual-code] | 2026-06-18 | Gemini 3.1 Pro Preview | [20.54% RHAE][continual-scorecard] | $774 | Submitted cost | Full public scorecard |
| [Polyphony Agent - ARC][polyphony-code] | 2026-07-07 | Qwen3.6 | [19.80% RHAE][polyphony-scorecard] | $115 | Submitted cost | Full public scorecard |
| [a-evolve MAS Evolved][aevolve-code] | 2026-04-09 | Claude Opus 4.6, high | [12.30% RHAE][aevolve-scorecard] | $5,300 | Submitted cost | Full public scorecard |
| [OpenClaw][openclaw-code] | 2026-05-15 | Claude Opus 4.7 | [5.20% RHAE][openclaw-scorecard] | $2,912 | Submitted cost | ARC Prize adaptation and full public scorecard |

RHAE means Relative Human Action Efficiency. It combines completion with action efficiency against first-attempt human play.

## How to read the cost column

Cost is not token usage. A cost total applies prices to cached input, uncached input, and output tokens.

Raw token totals remain the best direct usage comparison. Cached input, uncached input, and output totals permit a second comparison under any shared price schedule.

The comparison uses API-equivalent costs when public token details allow them. It retains submitted costs when those details are missing.

### Retrodict and baseline1

Retrodict and baseline1 have the cleanest cost comparison because both expose token usage and use the same GPT-5.5/GPT-5.6 price schedule:

- $5 per million uncached input tokens.
- $0.50 per million cached input tokens.
- $30 per million output tokens.

| Run | Score | Raw tokens | API-equivalent cost |
|---|---:|---:|---:|
| Retrodict, max | 99.86% | 0.66B | $654 |
| baseline1 textual world model, max | 95.97% | 1.20B | $918 |
| baseline1 executable world model, xhigh | 98.97% | 3.64B | $2,722 |

The baseline1 comparison does not use its $400 Community Leaderboard value. That value allocates subscription costs and is not an API-equivalent total.

### Other cost qualifications

- Tycho reports an API-equivalent estimate for one Opus 5 run.
- Schema's $6,447 covers retained winning runs. Its total conditional-rerun cost is higher and is not public.
- PRO-LONG reports $1,500 for pass@1 at 94.6% and $1,750 for selective best@2 at 97.4%.
- Prime Agent's official SVG places the Opus 5 endpoint at x=815.7. Its logarithmic axis maps x=100 to $10 and x=1360 to $30,000. Interpolation gives $944.19, which this comparison rounds to $944. Prime Intellect does not publish an exact total, underlying token pricing formula, input-token split, or per-game cost ledger.
- Prime Agent's [token chart][prime-token-chart] suggests about 414,000 output tokens per game. This is also a chart interpolation, not an exact published ledger.
- NOOA reports $13.28 per game, or $332 for 25 games.
- OPINE-World reports $1,040 on the leaderboard. Its repository also describes about $800 of Claude Max subscriptions.
- Submitted leaderboard costs do not follow one enforced accounting method.

## Score and run qualifications

- Tycho's selected row is one Opus 5 run across all 25 games. Its GPT-5.6 Sol run also scored 100.00%.
- Schema conditionally reruns games below a threshold with a second model. It retains the higher result for each game.
- PRO-LONG's headline score is selective best@2. Its 94.6% pass@1 result is closer to a single-run comparison.
- Prime Agent reports three Opus 5 runs at 95.0%, 95.2%, and 95.5%. The public median-run scorecard reports 95.2398%, 178 of 183 levels, and 11,245 actions. The article also reports 99.97% best@3 with all 183 levels complete, but does not define the aggregation procedure.
- Prime Intellect says the task prompt was the only ARC-specific change to its general agent. The prompt and exact run configuration are not public. Its repository contains no ARC-specific prompt, skill, or result artifacts.
- Read-Grep-Bash currently exposes one game on its scorecard. Do not compare 50.2% with full 25-game means.
- Tycho reports that AERA's evaluator can count several termination states as solved. This limits direct comparison.
- Arcgentica used the earlier 182-playable-level release. Current full-set reports use 183 levels.

## Scope

The table excludes the Human Intelligence Harness because it replays human solutions. It also excludes Duck Harness because its Kaggle score is not Public Demo RHAE.

Dates are result, submission, or announcement dates. They are not always paper publication dates.

## Main sources

- [ARC Prize Community Leaderboard][community-leaderboard]
- [Tycho paper][tycho-paper]
- [PRO-LONG paper][prolong-paper]
- [NOOA paper][nooa-paper]
- [Schema project page][schema-page]
- [Prime Agent article][prime-article]
- [Prime Agent median-run scorecard][prime-median-scorecard]
- [Retrodict and baseline1 token comparison][retrodict-readme]

[community-leaderboard]: https://arcprize.org/leaderboard/community

[tycho-code]: https://github.com/NIMI-research/Tycho
[tycho-scorecard]: https://arcprize.org/scorecards/08b98aa0-5df0-42c0-b501-856f553a21e9
[tycho-paper]: https://arxiv.org/html/2607.28287

[retrodict-code]: https://github.com/ryanbbrown/Retrodict
[retrodict-scorecard]: https://arcprize.org/scorecards/9c403765-db5b-40b1-beab-6fa3f40119b0
[retrodict-costs]: per-game-costs.md
[retrodict-readme]: ../README.md#performance

[schema-page]: https://schema-harness.github.io/

[baseline1-code]: https://github.com/astroseger/arc-3-agents-baseline1
[baseline1-scorecard]: https://arcprize.org/scorecards/34ea0a31-21f8-4a34-b5ee-5e26fdfc9a5c

[prolong-code]: https://github.com/alexisfox7/PRO-LONG
[prolong-paper]: https://arxiv.org/html/2607.20064

[prime-code]: https://github.com/PrimeIntellect-ai/prime-agent
[prime-announcement]: https://x.com/PrimeIntellect/status/2085087000764568010
[prime-article]: https://www.primeintellect.ai/blog/prime-agent
[prime-cost-chart]: https://www.primeintellect.ai/blog/prime-agent/arc-agi3-cost-scaling.svg
[prime-token-chart]: https://www.primeintellect.ai/blog/prime-agent/arc-agi3-scaling.svg
[prime-median-scorecard]: https://arcprize.org/scorecards/2af780b4-f2a1-43e9-a794-b23da3cd3f9f

[nooa-code]: https://github.com/NVIDIA-NeMo/labs-OO-Agents
[nooa-scorecard]: https://arcprize.org/scorecards/7a511ea0-dfa1-47ed-8a99-52a80f3cdbaa
[nooa-paper]: https://arxiv.org/html/2607.20709v1

[opine-code]: https://github.com/david-courtis/opine-world
[opine-scorecard]: https://arcprize.org/scorecards/dfa3eb8a-2d61-4ed2-9fab-874872d7185f

[vision-code]: https://github.com/vansh-one/arc-agi-3_Vision-CLv1
[vision-scorecard]: https://arcprize.org/scorecards/73aaed94-060a-44c6-b851-9997366eb89d

[rgb-code]: https://github.com/alexisfox7/RGB-Agent
[rgb-scorecard]: https://arcprize.org/scorecards/35d7852f-bb5c-4d40-b0e0-df501c27ef6f

[tell-code]: https://github.com/rednote-hilab/TELL
[tell-scorecard]: https://arcprize.org/scorecards/745891d9-7efa-414f-8ec4-ec62cbffc316

[dream-code]: https://github.com/NVIDIA/dream-team
[dream-scorecard]: https://arcprize.org/scorecards/831c83cf-b969-45fc-a6ce-27f9b3c4105c

[arcgentica-code]: https://github.com/symbolica-ai/arcgentica
[arcgentica-post]: https://www.symbolica.ai/blog/arc-agi-3

[aera-code]: https://github.com/farmountain/aera-arc3-paper
[aera-paper]: https://arxiv.org/abs/2605.25931

[continual-code]: https://github.com/feng-rrRay/Continual-Harness-ARC-AGI-3
[continual-scorecard]: https://arcprize.org/scorecards/ac3eeaf5-6ace-4d2d-bf29-9469fd00a57b

[polyphony-code]: https://github.com/Mininglamp-AI/polyphony-arc-3
[polyphony-scorecard]: https://arcprize.org/scorecards/d0895597-2bb5-4191-9b7b-ec97917da1aa

[aevolve-code]: https://github.com/A-EVO-Lab/a-evolve
[aevolve-scorecard]: https://arcprize.org/scorecards/c7147b87-aac6-498d-8916-8b37cf78756f

[openclaw-code]: https://github.com/arcprize/ARC-AGI-3-Agents/tree/main/agents/templates/openclaw_agent
[openclaw-scorecard]: https://arcprize.org/scorecards/4793f52c-ae2a-4622-a7e1-a84b06218c97
