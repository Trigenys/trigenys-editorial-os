# Creative Agent and asset manifest

Issue #11 creates/selects editorial assets without binding Editorial OS to one image provider.

## Boundary

The Creative Agent consumes:
- a versioned draft in `DRAFTED`;
- the exact vertical-pack snapshot persisted with that draft;
- a provider-agnostic `CreativePlanner`;
- optionally, a provider-agnostic `AssetProvider`.

It produces a versioned `AssetManifest` containing:
- the visual brief;
- exact asset IDs;
- aggregate rights status;
- provider identity/request count;
- the vertical-pack snapshot;
- the exact draft/manifest/asset versions Gate B must review.

## Text-only is first-class

A visual brief may set `text_only=true`.

When the vertical pack does not require assets:
- no image provider is required;
- no placeholder/fake image is created;
- the manifest contains zero assets;
- rights status is `CLEAR`;
- the workflow can progress `DRAFTED → ASSETS_READY`.

## Visual brief

A non-text-only visual brief contains named slots with:
- asset kind;
- editorial purpose;
- optional generation prompt;
- alt text;
- caption;
- safe filename;
- aspect ratio;
- requested output variants.

Vertical-pack visual rules constrain:
- whether assets are mandatory;
- allowed kinds;
- allowed aspect ratios;
- maximum asset count;
- alt/caption requirements;
- generated/external asset eligibility.

## Provider adapter

`AssetProvider.materialize(...)` receives one slot plus a stable idempotency key.

It returns provider-neutral metadata:
- origin: `GENERATED | EXTERNAL | PROVIDED`;
- URI/external ID;
- MIME type/dimensions/aspect ratio;
- source URL;
- license name/URL;
- rights status;
- generation metadata;
- output variants;
- provenance.

The provider adapter can be replaced without changing workflow logic.

## Provenance and rights

Origin and rights are separate concepts.

Generated assets must retain generation metadata. They are not automatically considered documentary evidence.

External assets must retain a source URL. If an external asset is marked `CLEAR`, license metadata is mandatory.

Provided assets must retain provenance.

Rights aggregate conservatively:
- all clear → manifest `READY`;
- any review-required → manifest `REVIEW_REQUIRED`;
- any restricted → manifest `BLOCKED` and workflow `BLOCKED`.

A `REVIEW_REQUIRED` manifest can reach `ASSETS_READY` so QA/Gate B can surface the unresolved rights state explicitly.

## Gate B snapshot

Every manifest persists an approval snapshot with:
- exact draft ID/version;
- exact manifest ID/version/status;
- exact asset ID/version/slot/kind/origin/rights/filename.

Later QA and Gate B consume this snapshot instead of reconstructing versions heuristically.

## Retry safety

The manifest input fingerprint covers:
- draft ID/version/fingerprint;
- full vertical-pack snapshot;
- planner identity;
- provider identity.

A repeated identical request reuses the existing manifest before calling the planner/provider again.

Each provider slot also receives a stable idempotency key derived from the manifest input fingerprint, covering crash/retry boundaries around remote provider calls.

## Video

`VIDEO` remains a domain asset kind, but no Remotion renderer is required for the MVP. A future renderer can implement the same `AssetProvider` boundary.
