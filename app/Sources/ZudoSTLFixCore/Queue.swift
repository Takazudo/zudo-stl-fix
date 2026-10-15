import Foundation
import Combine

public enum JobStatus: String, Sendable, CaseIterable {
    case queued = "Queued", checking = "Checking", repairing = "Repairing", verifying = "Verifying"
    case unchanged = "No repair needed", review = "Checked — review needed", ready = "Repair ready"
    case saving = "Saving", saved = "Saved", refused = "Cannot repair safely", incomplete = "Check incomplete", error = "Error", canceled = "Canceled"
    public var active: Bool { [.queued, .checking, .repairing, .verifying].contains(self) }
    public var canSave: Bool { self == .ready }
}

public struct Job: Identifiable, Sendable {
    public let id: UUID
    public let snapshot: Snapshot
    public let tolerance: Double
    public var status: JobStatus = .queued
    public var result: WorkerResult?
    public var message: String = ""
    public var savedURL: URL?
    public var warnings: [String] { result?.event.warnings?.map { warning in
        if case .object(let object) = warning, case .string(let text)? = object["message"] { return text }
        return warning.pretty
    } ?? [] }
    public var name: String { snapshot.original.lastPathComponent }
    public var details: String { "\(name)\n\(status.rawValue)\n\(message)\n\nWarnings\n\(warnings.joined(separator: "\n"))\n\n\(readableMetrics)\n\nSTL coordinate units are unspecified. Mesh validation does not certify printability, strength, fit, or shell containment.\n\n\(result?.event.summary?.pretty ?? "No complete report yet")\n\(result?.event.error?.pretty ?? "")" }
    public var readableMetrics: String {
        guard case .object(let summary)? = result?.event.summary else { return "" }
        func value(_ object: JSONValue?, _ path: [String]) -> String {
            var current = object
            for key in path { guard case .object(let map)? = current else { return "—" }; current = map[key] }
            switch current {
            case .string(let text)?: return text
            case .number(let n)?: return String(format: "%g", n)
            case .array(let values)?: return values.map { $0.pretty }.joined(separator: ", ")
            default: return "—"
            }
        }
        let before = summary["before"], after = summary["after"], repair = summary["repair_details"]
        return [
            "Triangles: \(value(before, ["triangles"])) → \(value(after, ["triangles"]))",
            "Invalid triangle pairs: \(value(before, ["surface_intersections", "defect_pair_count"])) → \(value(after, ["surface_intersections", "defect_pair_count"]))",
            "Dimensions X, Y, Z (STL coordinate units): \(value(after, ["dimensions_xyz"]))",
            "Bounds: \(value(after, ["bounds"]))",
            "Connected shells: \(value(after, ["connected_shells"]))",
            "Reoriented faces: \(value(repair, ["faces_reoriented"]))",
            "Maximum vertex displacement: \(value(repair, ["tiny_edge_cleanup", "maximum_vertex_displacement"]))",
            "Binary export quantization: \(value(repair, ["binary_export_maximum_vertex_quantization"]))",
            "Maximum bounds change: \(value(repair, ["maximum_bounds_coordinate_change"]))",
            "Engine version: \(value(.object(summary), ["engine_version"]))"
        ].joined(separator: "\n")
    }

}

/// The main actor owns only lightweight state. Snapshot, subprocess and destination I/O
/// live on separate actors/tasks. One loop awaits one worker before starting the next.
@MainActor public final class JobQueue: ObservableObject {
    @Published public private(set) var jobs: [Job] = []
    @Published public private(set) var inputMessages: [String] = []
    @Published public private(set) var importing = false
    @Published public var mergeTinyEdges = false
    @Published public var toleranceText = "0.00001"
    public var selectedTolerance: Double { mergeTinyEdges ? (Double(toleranceText) ?? .nan) : 0 }
    private let store: SnapshotStore
    private let worker: any WorkerServing
    private let exporter: Exporter
    private var loop: Task<Void, Never>?
    private var active: Task<WorkerResult, Error>?
    private var activeID: UUID?
    private var shuttingDown = false
    private var operations = 0
    private var imports = 0
    private var idleWaiters: [CheckedContinuation<Void, Never>] = []
    private func finishOperation() {
        operations -= 1
        if operations == 0 { let waiters = idleWaiters; idleWaiters.removeAll(); for waiter in waiters { waiter.resume() } }
    }
    public init(store: SnapshotStore, worker: any WorkerServing = ProcessWorker.bundled, exporter: Exporter = Exporter()) {
        self.store = store; self.worker = worker; self.exporter = exporter
    }
    public var hasUnsavedWork: Bool { importing || jobs.contains { $0.status.active || [.ready, .saving].contains($0.status) } }
    public var readyIDs: [UUID] { jobs.filter { $0.status.canSave }.map(\.id) }
    public func add(_ urls: [URL], tolerance requestedTolerance: Double? = nil) async {
        guard !shuttingDown else { return }
        let tolerance = requestedTolerance ?? selectedTolerance
        guard tolerance.isFinite, tolerance >= 0, tolerance <= 1 else { inputMessages.append("Tolerance must be finite and between 0 and 1 STL coordinate units."); return }
        operations += 1; imports += 1; importing = true
        defer { imports -= 1; importing = imports > 0; finishOperation() }
        for url in urls {
            do {
                let snapshot = try await store.snapshot(url)
                if shuttingDown { try? await store.remove(snapshot); return }
                if jobs.contains(where: { $0.snapshot.identity == snapshot.identity }) {
                    inputMessages.append("\(url.lastPathComponent): already in this queue (same file identity).")
                    try? await store.remove(snapshot)
                    continue
                }
                jobs.append(Job(id: snapshot.id, snapshot: snapshot, tolerance: tolerance))
                startIfNeeded()
            } catch { inputMessages.append("\(url.lastPathComponent): \(error.localizedDescription)") }
        }
    }
    public func clearMessages() { inputMessages.removeAll() }
    private func startIfNeeded() {
        guard loop == nil, !shuttingDown else { return }
        loop = Task { [weak self] in await self?.drain() }
    }
    private func drain() async {
        while !shuttingDown, let job = jobs.first(where: { $0.status == .queued }) {
            update(job.id) { $0.status = .checking }
            let worker = worker
            let task = Task { try await worker.run(snapshot: job.snapshot, tolerance: job.tolerance) { [weak self] phase in
                Task { @MainActor [weak self] in
                    self?.update(job.id) { item in
                        guard item.status.active else { return }
                        switch phase {
                        case "verifying": item.status = .verifying
                        case "repairing": if item.status != .verifying { item.status = .repairing }
                        default: break
                        }
                    }
                }
            } }
            active = task; activeID = job.id
            do {
                let result = try await task.value
                update(job.id) { item in
                    guard item.status.active else { return }
                    item.result = result
                    switch result.event.outcome {
                    case "repaired": item.status = result.candidate == nil ? .error : .ready
                    case "unchanged": item.status = (result.event.warnings ?? []).isEmpty ? .unchanged : .review
                    case "refused": item.status = .refused
                    case "incomplete": item.status = .incomplete
                    default: item.status = .error
                    }
                }
            } catch {
                update(job.id) { item in
                    guard item.status.active else { return }
                    if case WorkerFailure.timeout = error { item.status = .incomplete }
                    else if error is CancellationError { item.status = .canceled }
                    else if case WorkerFailure.canceled = error { item.status = .canceled }
                    else { item.status = .error }
                    item.message = error.localizedDescription
                }
            }
            let finished = jobs.first(where: { $0.id == job.id })
            if finished == nil || [.canceled, .error].contains(finished!.status) ||
                ([.incomplete, .refused].contains(finished!.status) && finished!.result?.report == nil) {
                // Cleanup follows worker reaping even when the user removed its canceled row.
                try? await store.remove(job.snapshot)
            }
            active = nil; activeID = nil
        }
        loop = nil
    }
    private func update(_ id: UUID, _ body: (inout Job) -> Void) { if let index = jobs.firstIndex(where: { $0.id == id }) { body(&jobs[index]) } }
    public func cancel(_ id: UUID) {
        guard let item = jobs.first(where: { $0.id == id }), item.status.active else { return }
        let wasRunning = item.status != .queued
        update(id) { $0.status = .canceled; $0.result = nil; $0.message = "Canceled; no output can be saved." }
        if wasRunning { active?.cancel() }
        else { Task { try? await store.remove(item.snapshot) } }
    }
    public func clearFinished() {
        let removed = jobs.filter { !$0.status.active && ![.ready, .saving].contains($0.status) }
        jobs.removeAll { item in removed.contains(where: { $0.id == item.id }) }
        let reapingID = activeID
        Task { for item in removed where item.id != reapingID { try? await store.remove(item.snapshot) } }
    }
    public func discard(_ id: UUID) {
        guard let item = jobs.first(where: { $0.id == id }), !item.status.active, item.status != .saving else { return }
        jobs.removeAll { $0.id == id }
        if id != activeID { Task { try? await store.remove(item.snapshot) } }
    }
    public func save(_ ids: [UUID], to directory: URL) async {
        guard !shuttingDown else { return }
        operations += 1; defer { finishOperation() }
        let protected = jobs.map { $0.snapshot.original }
        for id in ids {
            guard let item = jobs.first(where: { $0.id == id }), item.status.canSave, let candidate = item.result?.candidate else { continue }
            update(id) { $0.status = .saving; $0.message = "" }
            do {
                let output = try await exporter.save(candidate: candidate, stem: item.snapshot.original.deletingPathExtension().lastPathComponent, directory: directory, protectedInputs: protected)
                update(id) { $0.status = .saved; $0.savedURL = output }
            } catch {
                // A failed destination does not invalidate a verified private candidate.
                update(id) { $0.status = .ready; $0.message = "Save failed: \(error.localizedDescription). Choose another folder or retry." }
            }
        }
    }
    public func exportReport(_ id: UUID, to directory: URL) async {
        guard !shuttingDown else { return }
        operations += 1; defer { finishOperation() }
        guard let job = jobs.first(where: { $0.id == id }), let report = job.result?.report else { return }
        do {
            let output = try await exporter.exportReport(candidate: report, stem: job.snapshot.original.deletingPathExtension().lastPathComponent, directory: directory, protectedInputs: jobs.map { $0.snapshot.original })
            update(id) { $0.message = "Report saved: \(output.path)" }
        } catch { update(id) { $0.message = "Report export failed: \(error.localizedDescription)" } }
    }
    public func shutdown() async {
        shuttingDown = true
        for id in jobs.filter({ $0.status.active }).map(\.id) { cancel(id) }
        await loop?.value
        if operations > 0 { await withCheckedContinuation { idleWaiters.append($0) } }
        try? await store.cleanup()
    }
}
