# Spike — how much data is a validator actually seeing? (#1903)

**Question.** `list_issues_by_label` passes `--limit 100` with no pagination.
How many issues exist, how many does the fetch return, and does it matter?

**Why this one is different.** It was not found by a spike. **The operator found
it**, by reading the fetch and asking what the number was. That is worth recording
as prominently as the finding, because I had just reported the opposite: I
labelled 14 issues, watched `test_required_label_set` go green, and called the
work confirmed. The validator was green over a third of the data, and the issues
I had just labelled were in the two-thirds it could not see.

**Method.** Count the repository independently — through a paginated REST call,
not the capped path — and compare.

## Measured

| fetch | cap | reality | verdict |
|---|---|---|---|
| `list_issues_by_label` | 100 | **289** | truncating now |
| `list_open_issues` | 30 (default) | 289 | display path, cap is the operator's |
| `list_all_open_issues` | 500 | 289 | latent — the same defect waiting |
| `get_sub_issues` | — | — | **paginates** |

The window was **#1620–#1901** — the newest hundred. Every issue below it was
invisible:

    #1098 #1099 #1100 #1101 #1102 #1109 #1141 #1207 #1313 #1314

all ten missing a phase label, all ten outside the window, and
`test_required_label_set` PASSING. With the complete set it fails on exactly those
ten, which is what it should always have done.

## Findings

1. **The truncation kept the NEWEST rows.** So the issues least likely to be
   revisited — the oldest — were exactly the ones the check could not reach. A
   cap on a recency-sorted listing is not a random sample; it is a blind spot
   aimed at the stalest data.

2. **The asymmetry is the whole tell.** `get_sub_issues`, ten lines below in the
   same class, has always used `--paginate`. Both return a plain `list`. Nothing
   at either call site distinguishes a complete answer from a prefix — so this
   was invisible rather than merely missed. An unmarked type, not carelessness.

3. **Raising the cap only defers it.** At exactly N rows, "there were N" and
   "there were more" are the same observation. So reaching the cap now RAISES:
   completeness is unknown, and unknown is not clean.

4. **It composes with #1896.** The prefetch stores exceptions; #1896 made the
   fixtures turn a stored exception into COULD_NOT_CHECK instead of a skip. So a
   truncated fetch now reaches the validator as a refusal rather than as a short
   list. Neither fix would have been sufficient alone.

## The lesson that is not about pagination

Four times in this session a check reported clean because it could not fail on
the thing being checked: the pre-push heal, `_fetch_issue`, the fail-open
fixtures, and this. **This is the first one I caused rather than found** — I
labelled the issues, then read a validator that structurally could not examine
them, and reported it as confirmation.

Reading a green is not verification. The question is always what the check could
have seen, and that is a number you have to go and get.

## Disposition

No harness kept: the measurement is a paginated census, and it now lives as
E077-SMOKE-001 rather than as a script — it should run forever, not once.
