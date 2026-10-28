# Rider-zone conversion: research and validation evidence

Public summary of implementation research dated 2026-09-10, with comparisons
against upstream conversion checked on 2026-10-15. This note accompanies
[PR #63](https://github.com/jorge-huxley/intervalssync/pull/63).

All numerical examples below are synthetic. No athlete values, account or
deployment identifiers, credentials, private payloads, or generated state are
included. This note documents implementation reasoning, not training advice.

The revised upstream contribution uses the existing conversion and HR-mode
behavior, not the strict adapters described as historical research below.
Same-input regression tests cover seven power slots, five HR slots, custom
labels/boundaries, fractional thresholds, rounding, and the legacy power cap.

## What the research addressed

The downstream requirement was to transfer existing Intervals.icu settings,
preserve unselected destination fields, and verify the stored result. It did
not authorize estimating thresholds or replacing configured boundaries with
values calculated from a textbook zone model.

The research separated three decisions:

1. Representation: percentages versus watts, integer rounding, open-ended
   markers, and the destination terminal cap.
2. Coarsening: which boundaries to retain when fewer destination slots exist.
3. HR mode: which destination table is active and which threshold basis it uses.

These decisions need explicit compatibility policies. They are not all implied
by the number of zones or by the physiological literature.

## Source material and its limits

- [TrainingPeaks' calculator documentation](https://help.trainingpeaks.com/hc/en-us/articles/360017420092-Zones-Calculator-Overview)
  distinguishes LTHR-based Friel HR methods from maximum-HR and HR-reserve
  methods. It also supports custom settings. This provides model vocabulary;
  it does not require a relay to recognize particular label strings.
- [Coggan's description of power zones](https://www.trainingpeaks.com/blog/power-training-levels/)
  describes a seven-level power system relative to threshold, with a distinct
  neuromuscular level. It does not specify an iGPSPORT seven-to-five conversion,
  terminal cap, or rounding rule.
- [Stages' HR-zone manual](https://manuals.stagescycling.com/en/dash-m200-l200/user-manual/settings/user-settings/heart-rate-zones/)
  documents Friel preset boundaries, a threshold basis, and custom zones. It is
  evidence about that manufacturer's representation, not proof of iGPSPORT's
  firmware behavior or an exact label match for every Intervals configuration.
- [Joe Friel's current guide](https://joefrieltraining.com/a-quick-guide-to-setting-zones/)
  discusses several HR bases and notes revisions to his methods. A model name
  alone therefore should not be treated as a timeless, complete wire contract.

The literature motivated preserving the configured source boundaries rather
than inventing new ones. Choosing a particular coarsening policy or rejecting
custom labels remains an engineering decision, not a scientific necessity.

## Why the initial implementation used strict adapters

The targeted source configuration was compatible with an LTHR-based seven-band
HR scheme and a seven-band FTP-based power scheme. The observed destination
exposed five HR rows, seven power rows, and alternative HR tables.

The initial HR adapter retained the first four upper boundaries and combined
the three highest bands into one final destination band. It selected the LTHR
table for the recognized HR scheme. The initial power adapter converted finite
percentages to integer watts using decimal half-up rounding and preserved the
fetched destination terminal cap. The Intervals `999` open-zone marker was not
multiplied by FTP.

Named-model recognition was a conservative gate before applying those specific
policies. It was not required to copy explicit numerical boundaries. It also
has a compatibility cost: renamed, translated, or custom labels can be rejected
even when their numerical boundaries are usable.

## Actual comparison with the existing conversion

These outputs were computed using the existing `map_power_zones` and
`map_hr_zones` functions and the proposed strict adapters. Arrays show upper
boundaries, not complete API payloads.

### Seven power zones into five slots (synthetic only)

No five-slot power table was observed in the live configuration. That account
exposed seven power slots and five HR slots. This hypothetical reduction was
an adapter test, not evidence of a defect in the live seven-slot conversion.

Synthetic FTP: `250 W`; percentages: `[55,75,90,105,120,150,999]`;
destination terminal cap: `2500 W`.

| Conversion | Resulting upper boundaries in watts |
| --- | --- |
| Existing | `[138,188,225,375,2500]` |
| Proposed strict adapter | `[138,188,225,263,2500]` |

The existing conversion preserves the first three boundaries and the last
finite source boundary before the terminal cap. The proposed adapter preserves
the first four and combines the remaining upper bands. This is a different
coarsening policy; this example alone does not establish that the existing
policy is wrong.

With seven power slots, the existing mapper retains all six finite source
boundaries (after legacy rounding) and replaces the open-ended sentinel with
its terminal cap. There is no seven-to-five power reduction in that live shape.

Rounding is a separate difference: `250 * 1.05 = 262.5`. The existing ties-to-even
rounding produces `262`; positive half-up produces `263`. For a seven-slot
destination with the same synthetic input, the results are:

- Existing: `[138,188,225,262,300,375,2500]`.
- Proposed: `[138,188,225,263,300,375,2500]`.

The existing power mapper sets a terminal cap of `2500`, whereas the proposed
adapter retains the fetched cap. The examples above deliberately use the same
cap to isolate the other differences. Neither the literature nor these tests
establishes the correct cap policy for every iGPSPORT device.

### Seven HR zones into five slots

Synthetic source upper bounds: `[120,145,165,175,185,190,195]`;
maximum HR: `195`; LTHR: `180`; labels recognized by the proposed adapter.

| Conversion | Resulting upper boundaries in BPM |
| --- | --- |
| Existing | `[120,145,165,175,195]` |
| Proposed strict adapter | `[120,145,165,175,195]` |

There is no numerical boundary improvement in this example. The difference is
that legacy profile sync selects maximum-HR mode and its table, while the
recognized strict adapter selects LTHR mode and its table.

### Custom names with the same boundaries

Replacing the labels above with `Custom 1`, `Custom 2`, and so on does not change
the existing numerical mapping. The proposed recognizer returns `unknown` and
blocks the interval-settings write group. That restriction comes from the
chosen recognition policy, not a demonstrated inability to transfer the values.

## Live API evidence recorded on 2026-09-10

The separate release-acceptance record documents real rider-settings writes
and read-back checks in the downstream installation:

- Source HR/power models were recognized; changed selected fields were written.
- A first read-back exposed server-regenerated zone-row IDs. The verifier was
  corrected to ignore only those server-owned IDs, retaining checks of member
  values, zone boundaries/metadata, inactive tables, and the power cap.
- Subsequent in-memory comparisons confirmed the chosen LTHR mode, expected HR
  and power endpoints, the retained power cap, and preservation of required
  personal-profile fields.
- A later status-only run found all ten supported fields unchanged and proposed
  no writes.

This establishes successful API persistence for the configuration exercised.
It does not establish comprehensive mobile-editor rendering, device-delivery
behavior, firmware recalculation behavior, or clinical/physiological superiority
of the chosen conversion. Workout secondary-cadence testing in PR #62 is a
different feature and is not evidence for HR calculation-mode behavior.

## Implication for the upstream review

Field selection, extra personal fields, dry-run, and read-back verification can
be implemented around the existing zone conversion. This research explains the
original stricter policy, but does not require it to become a new default.

If rounding, terminal-cap preservation, model-specific coarsening, or HR-mode
selection are proposed separately, each should have a focused compatibility
argument, tests, and the relevant app/device evidence. Those strict-policy
changes have been removed from this upstream contribution and remain separate
downstream behavior. This historical research does not justify changing the
original project's zone policy implicitly.
