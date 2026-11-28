# Future: Unified Resources and Data Tracking

**Status:** Architectural agreement from the discussion of 2026-11-28. Not implemented.
**Scope:** `almasi.a` and `almasi.o`. MCP and Web are subsequent consumers.
**Baseline:** A master at `bc166d0edf63d202e002abe4dda4df62bc5b882b`; O Changes rename in [PR #25](https://github.com/WordWield/almasi.o/pull/25), head `8aa5f2f533062d9da0d74ea0baa45d428d22e473`.

This document records the architectural decisions made in the discussion, including the alternatives that were rejected and the problems that remain open. It does not describe the current implemented API. Examples below express the intended contract, not executable examples of the current system. The current implementation remains documented in [architecture.resource.md](architecture.resource.md).

## 1. Intent and necessary symmetry

We have multiple observable data systems. Filesystem and O differ in how they read, write, identify and discover their data. They should not differ unnecessarily in how observation is represented, how dependencies are collected, how changes reach a consumer, or how observation ends.

Separate the data from the observation of the data. A Resource represents an observed set of identities, not a particular data type or storage implementation. A Resource can observe files, O entities, or both at once.

The common subscription machinery belongs in Core. Source-specific behavior belongs to the service that owns the source. Preserve the existing behavior and performance of the underlying data systems unless a specific architectural change requires otherwise.

Do not introduce a new entity merely to connect the existing entities.

## 2. Entities and responsibility

| Entity | Responsibility |
| --- | --- |
| `a.Resource` | Own the observed IDs, the upstream subscription identity and the observation lifecycle; receive changes, maintain membership and propagate changes upstream. |
| `DataManager` | Common base class for observable data services. Own the common observation and matching machinery, retaining references to the Resources it observes. |
| `a.services.Filesystem` | Filesystem-specific observation, matching, event interpretation, cache invalidation and watcher lifetime. |
| `o.services.Changes` | O-specific committed changes, observation and matching; source of local write tracking. |
| `a.services.Tracker` | Common scoped collection of read/write identities and construction or replacement of a Resource's dependencies. |
| `File`, `Directory` | Own file and directory behavior and explicit creation of a Resource for their data. |
| `FilesystemItem` | Common filesystem carrier identity and existing shared File/Directory functionality, independent of Resource. |

DataManager is a base class of the existing observable services, not a new central service or a separate intermediary between Resource and those services. O and Filesystem retain their necessary asymmetry in source-specific behavior.

There is no universal DataItem base class. All observable data need identity, not necessarily a common Python ancestor. O's existing data classes do not have to inherit a new class to participate.

## 3. Identity

All observable data across the system have globally unique IDs:

- Files and directories: canonical absolute physical paths (strings).
- O entities: existing integer IDs.

The distinction is already covered by these identity systems. There is no need to introduce a composite identity, manager-qualified key, ID wrapper or new identity registry. The Resource can use one ordinary set containing both strings and integers.

Directory identity exists independently of the identities of its members. The path of the directory itself is an observable ID.

This is a system invariant: any future observable source must preserve global uniqueness. This document does not introduce an identity allocator or prescribe a new ID representation for future sources.

## 4. Resource

### 4.1. Observed identities

The Resource owns `observed_ids`, a set of the identities it observes. It is the authoritative set, not a copy of a dependency set owned by a DataManager.

A DataManager holds references to its subscribed Resources and consults the Resource's set when matching an incoming change. The agreed representation was a list of Resource references, rather than a dictionary keyed by dependency sets or an independent set of IDs for each manager registration.

A single Resource may contain IDs from more than one data manager, from more than one directory and from individual files or O entities. No Resource-level collection-specific state is necessary.

The Resource exposes an update operation that receives changes as a mapping from ID to change metadata (the discussion also allowed None in the metadata representation; the exact encoding has not been fixed). The logical change kinds are:

| Change | Resource action |
| --- | --- |
| `ADDED` | Add the ID to `observed_ids`. |
| `REMOVED` | Remove the ID from `observed_ids`. |
| `CHANGED` | Keep the ID in `observed_ids`. |

Propagate the changes to the higher-level subscriber. The Resource does not infer source-specific membership or inspect filesystem paths to decide which additional changes should have occurred. That is the responsibility of the source manager.

The three event kinds are common. DataManager was proposed as the owner of the class constants; the concrete metadata schema and representation of those constants are not finalized.

### 4.2. Subscription and lifetime

Intended API:

~~~python
resource.subscribe(subscriber_id)
resource.unsubscribe()
~~~

The subscriber ID identifies the upstream subscription, for example an MCP resource URL. This replaces the earlier callback-registration model at the Resource boundary. The agreed interface has one upstream subscription identity per Resource, rather than a set of independently cancellable callback registrations inside Resource. The upstream layer owns any necessary client fan-out.

Creation of a Resource, including leaving a tracking context, does not start observation. Observation begins when the higher-level subscriber calls `resource.subscribe(subscriber_id)`.

On subscription the Resource sends `ADDED` for all its current observed items. This is the initial state of the observed set, not an assertion that those items were newly created on disk or in O. Directory subscription includes the directory's own ID in this state.

Observation ends in either case:

1. `observed_ids` becomes empty.
2. The higher-level subscriber calls `resource.unsubscribe()`.

In both cases observation is stopped and the Resource is released. A manager must no longer retain it as an active observation. If the Resource observes multiple sources, stopping it must stop the corresponding observation in all those sources. A source's underlying shared watcher is needed only while there are active observations requiring it.

Deliver the removal event to the upstream subscriber even when the last ID is removed. Release does not mean deleting the underlying data.

Removal is terminal for an individually observed identity: when an item is removed, it leaves the observed set. If it later reappears with the same ID, it is not automatically observed again. An explicit new observation is possible. The directory case is different because a still-observed directory admits newly added members through its own identity.

The exact mechanism for delivering to a subscriber ID and releasing upstream ownership remains to be specified. No callback registry, URI routing implementation or lifecycle mechanism beyond the agreed contract is prescribed here.

### 4.3. Reading is not the common Resource operation

Data observation and data access are different responsibilities. File reading, O computation and stream-range reading do not share a single necessary read signature.

Do not force every Resource to define a common `read()` operation merely because the old Resource class did. The old Computed specialization is removed: file and O observations use ordinary Resource.

The precise location and contract of a cached computed result after this change, and the MCP read boundary, remain to be specified. Do not silently remove the existing ability to obtain computed results or read streams when removing the old common read contract.

## 5. DataManager

DataManager is the common base for `a.services.Filesystem` and `o.services.Changes`.

A manager watches its own source and delivers the relevant change mapping to each subscribed Resource. The common representation is the manager's collection of Resource references and the Resource's own `observed_ids`.

Exact ID membership is a set lookup. O uses exact ID matching. Filesystem additionally understands whether an event belongs to an observed directory, since it is the only source with that directory-membership responsibility.

Do not duplicate the observed set in the manager or group subscriptions by a frozenset key. The rejected grouping model was a dictionary of dependency sets to callbacks (including the variant mapping a frozenset to a set of callbacks). A Resource's dependency set can change while the Resource and its subscriber remain the same. Sharing a mutable membership set or re-keying a dictionary around it introduces unnecessary machinery. Keeping the set in Resource and referencing that Resource avoids the competing ownership.

DataManager does not need to know about MCP URLs, controller methods, application state or Web.

How Resource selects and registers with the applicable DataManagers, and the precise public registration methods of DataManager, are not yet specified. Do not invent a central manager registry just to fill this gap.

## 6. Filesystem

### 6.1. File and Directory are not Resources

Remove Resource from the File/Directory inheritance tree. Remove `FilesystemResource` as a class and name.

File and Directory do share genuine functionality, so the existing `lib/filesystem_resource.py` is to become `lib/filesystem_item.py`, with class `FilesystemItem`. It does not inherit Resource.

Preserve the common carrier identity:

- Source library (`__lib__`) and effective namespace (`_namespace_lib`).
- Canonical path (`__path__`) and logical route (`__route__`).
- Existing getters `get_path()`, `get_lib()`, `get_namespace()`, `get_route()`, `get_name()`, `get_stem()`.
- Existing carrier representation and canonical Filesystem service access where needed.

Remove the old inherited observation hook and callback subscription delegation. Do not add a separate universal DataItem class, nor define a base method simply to give two distinct implementations the same name.

File owns its file access; Directory owns its namespace and collection behavior. Both provide `subscribe()`, but the methods create different initial observed sets. The methods return ordinary Resources, not active observer handles.

### 6.2. Explicit observation

Intended usage:

~~~python
resource = file.subscribe()
resource.subscribe(subscriber_id)
~~~

A file observation begins with the file's own path as its only observed ID.

~~~python
resource = directory.subscribe()
resource.subscribe(subscriber_id)
~~~

Directory provides its own initial listing: the directory's own ID and the IDs of its contained observable items. The Directory determines the composition of its collection; Filesystem must not enumerate the directory to construct this initial set. It receives the Resource with its observed set already populated.

The exact listing depth and treatment of nested directory IDs, symlinks and inherited items must respect the existing Directory contract; their detailed mapping to the new observation semantics has not yet been decided.

### 6.3. New files and directory identity

A native watchfiles subscription to a directory receives additions for paths that were not previously known. `awatch` provides batches of change-kind/path pairs to its caller; it does not require prior subscription to each child path. It does not guarantee a separate modified event on the parent directory when a file is added.

A Resource observing a directory might start with:

~~~python
observed_ids = {
	'/app',
	'/app/main.js',
}
~~~

When Filesystem receives an addition for `/app/style.css`, the new file is not yet in the set. But `/app` is. Filesystem matches the new file to the observed directory and sends `ADDED` for the file's path. Resource adds that ID and propagates the event.

There is no new collection ID field in Resource, no extra collection subscription object and no need for a second set merely to keep an empty directory alive.

When the last child is removed, the directory's own ID remains. Observation continues and newly added children can be observed. Only removal of the directory's own ID (and all remaining observed IDs, if any) or explicit unsubscribe ends observation.

A file content change belongs to the file ID. Do not track or emit a synthetic parent-directory change merely because one of its files was modified. Directory observation concerns its membership as well as the files included in the observed set.

### 6.4. Removal of a directory

A native watcher might report removal of a directory without a separate removal for every descendant.

Filesystem owns this interpretation. It must send `REMOVED` for all affected observed IDs, including the directory itself and the observed descendants that have disappeared. It can use the identities already present in the Resource's set; the Resource does not need to understand path hierarchy or query the filesystem.

The alternative of keeping a separate collection_id in Resource and clearing the whole set on its removal was rejected: a Resource can observe several directories, unrelated files and O entities. Removing one collection must not remove the other dependencies.

### 6.5. Physical changes and namespace ownership

Filesystem watches physical changes and owns source-specific event matching, including cache invalidation before consumers read changed data. The current implementation uses watchfiles with shared physical watcher roots and a service observation loop; these are implementation facilities, not new Resource responsibilities.

The existing Filesystem service also resolves effective namespace membership across inherited library roots. Directory, not Filesystem, owns the listing and effective namespace composition. Do not preserve that responsibility in two owners.

The exact runtime handling of an inherited visible file changing, an overridden hidden file changing, or deletion of an override exposing an inherited file has not been settled for the new API. These existing cases must be considered explicitly rather than silently losing behavior. No new inheritance-resolution machinery is authorized here.

Keep the change kind from the source instead of reducing every source event to an undifferentiated changed path where the kind is meaningful. The agreed common event names are logical names, not a requirement that watchfiles use those exact names.

## 7. Tracker

Tracker belongs to Core, not O. It provides two context managers with the same Resource contract.

~~~python
with a.services.Tracker.track_reads() as resource:
	value = file.read()
~~~

~~~python
with a.services.Tracker.track_writes() as resource:
	directory.write('example.txt', 'content')
~~~

Both start collecting identities at entry and stop collecting at exit. Reads and writes differ by the operation being observed, not by the kind of Resource they produce.

Both accept an existing Resource:

~~~python
with a.services.Tracker.track_reads(existing_resource) as resource:
	value = file.read()
~~~

~~~python
with a.services.Tracker.track_writes(existing_resource) as resource:
	directory.write('example.txt', 'content')
~~~

When no Resource is supplied, the context creates one. When an existing Resource is supplied, its identity and upstream subscription are preserved. On successful exit, the collected IDs replace its previous set, not merely extend it. This is how recomputation replaces dependencies. Source observation follows the new set if the Resource is already subscribed; an inactive Resource stays inactive until a higher-level subscriber subscribes. An empty resulting set follows the agreed release rule.

The discussion established successful replacement and preservation of prior dependencies on a failed recomputation. Do not publish an incomplete replacement set on exception.

Tracker collects dependencies, not a history of operations. In particular, track_writes observes the IDs of successful changes that survive; removed IDs do not remain tracked and their later reappearance does not restore observation.

Local write tracking is scoped to the current execution context. Existing O behavior distinguishes the current thread and async task, other threads/tasks, remote changes and successful commits versus rolled-back changes. Preserve those distinctions. A notification received from another process is not a write performed by the local tracking context. Nested and concurrent scopes must not corrupt one another.

Read/write tracking of a file records the file's ID, not its parent directory. Explicit observation of a directory's composition is the Directory subscription described above. Do not turn every file access into observation of an entire collection.

File and Directory perform filesystem access; filesystem tracking must include the actual accesses that satisfy the tracking contract. The precise read interception points (including already cached file/directory reads), write-success points and treatment of failed/partially successful filesystem operations are not yet fixed.

The read-to-observation race between collecting dependencies and beginning observation is consciously deferred to a subsequent version. The present agreement does not require the earlier O-specific in-flight change verification mechanism or introduce a new snapshot/revision protocol to close that gap.

## 8. O

O already has unique integer identities. It does not require a DataItem ancestor, a new identity system or changes to the internal persistent data classes.

O's Resource observation is exact-ID based. Once a Resource is observing O IDs, its normal incoming events are `CHANGED` and `REMOVED`. There is no directory-style addition of new members to its set. The initial `ADDED` notification on subscription is still required by the common Resource contract. New dependencies discovered by recomputation are handled by Tracker's replacement operation, not by giving O filesystem collection semantics.

### 8.1. Writes

All successful persistent writes already pass through the existing Changes service from Memory's successful commit path. Tracking writes naturally belongs at Changes. No change to `root/services/memory.py` is required for tracking.

Do not move tracking into individual setters, collection operations or other internal O classes. Preserve the existing distinction between local committed writes and remote invalidation.

The existing Changes publication currently carries a set of IDs (or None) and a local/remote flag. How Changes obtains the necessary logical REMOVED information from that existing contract, and how the existing full-invalidation signal None is represented in the new observation contract, still require verification. The agreed exclusion of Memory from the change list is not a claim that those questions have already been solved.

### 8.2. Reads and performance

Changes observes writes; it cannot discover which cached attributes were read. O already has a specialized mechanism in its current Tracker: it temporarily intercepts fields, collection access, serialization, tree rendering, class enumeration and existence checks while a tracked read is active. Ordinary reads outside a scope retain their fast existing path.

Keep the O-specific read interception on the O side, and use the common Core Tracker for the collected identities and Resource lifecycle. Do not reproduce the read interception in generic Core, and do not change the O data classes just to introduce a shared abstraction.

`root/services/tracker.py` therefore retains only the necessary O-specific read interception responsibility; the generic scope/Resource machinery moves to Core. Its exact integration point with Core Tracker has not been finalized.

Preserve existing read transparency and performance. The current O implementation also handles prospective identities and class membership observations; verify those use cases against the agreed new lifetime rule rather than assuming that they are equivalent to ordinary reads of existing objects.

### 8.3. Computed and Transport

The old specialized `o.resources.Computed` is no longer required as a resource type. Filesystem and O both use ordinary Resource. Its old dependency ownership and subscription machinery must not survive as a parallel mechanism.

Transport remains responsible for interprocess propagation. Adapt it to the revised Changes contract while preserving remote invalidation, local-only propagation where necessary, cache correctness and reconnect behavior. Do not introduce InnerChanges/OuterChanges or another intermediary to divide Changes solely for this purpose.

## 9. Writable, commands, Stream and Log

### 9.1. Writable is removed

The old `a.resources.Writable` owns an in-memory value, provides read/write and notifies after writes. It has no additional capability that requires a separate observable data system.

A temporary file was considered, including a RAM-backed filesystem, but rejected for commands: the normal filesystem watcher delivery introduces latency independent of disk I/O.

Commands should use O. O already provides identity, writes, observation and interprocess synchronization. Web owns the command data and its lifecycle. The exact O representation of commands (for example a value or queue) is a Web design decision, not an additional Core resource type.

Delete `root/resources/writable.py` and migrate its consumers. No memory-file abstraction, new writable data manager, or temporary-file command service is required in A or O.

### 9.2. Stream uses the singleton-set case

Stream cannot simply be replaced by an ordinary whole-file read/write API. Its necessary data behavior is already implemented:

- Temporary-file byte storage with absolute byte positions.
- Independent readers and bounded/circular retention when configured.
- Non-consuming range reads.
- Synchronized access.
- End-of-input state (`closed`); closing does not discard the retained bytes.

The problem with the previous architecture was the specialized read signature under a common Resource read method, together with treating a stream as a singular resource and other observations as sets.

The agreement is that a stream is observed as an ordinary Resource with a set containing one file ID. MCP must still receive Resource notifications for a stream. There is no separate stream observation mechanism, no stream-specific DataManager, and no requirement for a second Resource hierarchy.

Conceptually:

~~~python
observed_ids = {stream_file_path}
~~~

Stream keeps its necessary specialized data access and storage semantics. The ordinary Resource represents its observation. The exact class composition/inheritance and the connection to MCP's stream read operation are not yet decided; do not infer that the old range-read API can be deleted.

The present Stream uses `tempfile.TemporaryFile`, which does not necessarily have an observable filesystem path. To observe it through Filesystem, its data file must have an observable identity/path. Also, closing a stream changes its logical state even when the bytes do not change: the existing close notification must be preserved as a CHANGED notification. The precise means of generating that notification is still open, as are the notification timing and temporary-file lifetime details. Do not introduce a new service solely to implement these details without demonstrating its necessity.

### 9.3. Log

Log specializes Stream with timestamp-indexed reads. It currently uses a second temporary file for its index, publishes the index with the bytes under the stream lock, and supports independent readers.

Preserve this specialized read behavior. The index is implementation data belonging to Log; the agreement about a stream's ordinary one-file Resource does not require a separate observable Resource for its index.

The detailed migration of Log, including the ordering of notification relative to publication of the index, has not been agreed. It must be considered along with Stream, not accidentally removed with Writable or Computed.

## 10. Review of the six identified logical holes

| Initial concern | Resolution |
| --- | --- |
| Identity collisions between managers | Global identity uniqueness already exists: physical path strings and O integers. |
| Matching an added file not yet present in the observed set | Directory's own ID is present; Filesystem matches membership and sends ADDED. |
| Directory deletion can omit events for descendants | Filesystem sends REMOVED for all affected observed IDs; never clear unrelated dependencies in Resource. |
| Resource retained despite having no subscriber | Observation begins only on upstream subscribe and ends on explicit unsubscribe or an empty observed set. |
| Track writes loses information about deleted data | Intentional: Tracker tracks surviving identities, not history; deletion ends observation of that identity. |
| Computed dependencies can change | Both tracking contexts take an existing Resource; replace its dependency set while preserving identity and subscriber. |

These are resolved at the architectural-contract level. They do not establish that every implementation detail is solved or that the current code already implements the contract.

## 11. Implementation scope

These are the two repositories whose core observation implementation must change. The following is the current expected source-file scope, revised throughout the discussion. It is not a permission to add mechanisms or a claim that every remaining consumer has already been inspected.

### almasi.a

| File | Intended change |
| --- | --- |
| `lib/data_manager.py` | New common base class. |
| `root/services/tracker.py` | New common tracking service. |
| `lib/resource.py` | Ordinary observed-ID Resource and new subscription/lifetime contract. |
| `lib/filesystem_resource.py` -> `lib/filesystem_item.py` | Rename the shared carrier; remove Resource inheritance and the old subscription mechanism. |
| `lib/file.py` | Use FilesystemItem; explicit observation and tracking. |
| `lib/directory.py` | Use FilesystemItem; own collection listing, explicit observation and tracking. |
| `root/services/filesystem.py` | DataManager specialization; matching and change delivery. |
| `lib/reloadable.py` | Migrate existing file subscription consumer. |
| `root/resources/writable.py` | Delete. |
| `root/resources/stream.py` | Adapt to ordinary one-file observation while retaining stream data behavior. |
| `root/resources/log.py` | Review/adapt if required by Stream changes; preserve the existing Log contract. |
| `a.py` | Update exported classes. |

Do not create `lib/data_item.py`. FilesystemItem preserves existing concrete commonality instead.

### almasi.o

Use the Changes rename from O PR #25 as the architectural baseline.

| File | Intended change |
| --- | --- |
| `root/services/changes.py` | DataManager specialization and local committed write tracking. |
| `root/services/tracker.py` | Retain only O-specific read interception and integrate with Core Tracker. |
| `root/services/transport.py` | Adapt existing change propagation to the new contract. |
| `root/resources/computed.py` | Delete the specialized resource type; use ordinary Resource. |

Explicit exclusions agreed in the discussion:

- `root/services/memory.py`: existing successful commit publication already supplies Changes.
- `root/t.py`, `root/t_meta.py`, `root/list.py`, `root/dict.py`, `root/serializer.py`, `root/tree.py`, `root/services/entity.py`: no new DataItem inheritance or tracking modifications; preserve the existing O read-interception mechanism.

### Tests, documentation and later consumers

Migrate the existing native tests in both repositories. In A this includes resource subscriptions, filesystem, directory, reloadable, stream, log and the obsolete Writable tests. In O this includes Tracker (including transparency, public API and write tracking), Computed, Changes, write tracking and Transport tests. Update the corresponding performance runners and architecture documentation when implementing the contract. Run the existing performance comparisons, particularly O ordinary access and tracked reads/writes; do not assume unchanged performance.

MCP and Web must subsequently migrate from the previous Resource/read/subscription APIs, including the computed read boundary, file/directory resources, Stream/Log and command storage. They are not additional Core data managers. This document does not decide their precise migration implementation.

## 12. Open details (not decisions)

The discussion deliberately left the following implementation details unresolved:

- Concrete event metadata schema, class-constant representation, source registration and upstream subscriber-ID notification/release API.
- Exact synchronization of membership changes, replacement and delivery, apart from the intentionally deferred read-to-observation gap.
- Directory listing depth and effective namespace/physical identity behavior under inheritance, override changes, nested directories and symlinks.
- File/directory tracking interception points, including cached reads and failed/partial writes.
- O-specific read interception integration with Core, prospective-ID observations, how the existing Changes publication distinguishes removal, and full invalidation on Transport reconnect.
- Storage/access of a cached computed result and how MCP reads it after the removal of Computed and the common read signature.
- Stream's observable backing path, closure notification, publication ordering for Log, ownership of temporary files, and exact stream/MCP read integration.

No proposed solution to these items is implied by recording them. The architecture's test is whether every existing necessary capability survives without redundant state, responsibility or mechanisms.

## 13. Architectural conclusion

Resource owns observation. Tracker discovers dependencies. DataManager unifies the observation machinery of existing observable services. Source managers retain only their necessary source-specific differences. File and Directory retain their necessary carrier commonality in FilesystemItem.

There is no universal DataItem, no FilesystemResource, no specialized Computed or Writable Resource, no independent stream observation machinery, no duplicate observed-ID set, and no separate collection field in Resource.

The objective is one observation architecture for files, directories, O and streams, without making the data themselves artificially alike.
