import XCTest
import CryptoKit
import Darwin
@testable import ZudoSTLFixCore

private actor ControlledWorker: WorkerServing {
    var starts: [UUID] = []
    var continuations: [UUID: CheckedContinuation<WorkerResult, Error>] = [:]
    var simultaneous = 0
    var maximumSimultaneous = 0
    func run(snapshot: Snapshot, tolerance: Double, progress: @escaping @Sendable (String) -> Void) async throws -> WorkerResult {
        starts.append(snapshot.id); simultaneous += 1; maximumSimultaneous = max(simultaneous, maximumSimultaneous)
        defer { simultaneous -= 1 }
        return try await withCheckedThrowingContinuation { continuations[snapshot.id] = $0 }
    }
    func complete(_ id: UUID, outcome: String = "unchanged", warnings: Bool = false, candidate: VerifiedArtifact? = nil, report: VerifiedArtifact? = nil) throws {
        let payload: [String: Any] = ["protocol_version": 1, "job_id": id.uuidString, "event": "result", "outcome": outcome,
            "validation_status": "PASS", "summary": [:], "warnings": warnings ? [["code": "review", "message": "Review geometry"]] : []]
        let event = try JSONDecoder().decode(WorkerEvent.self, from: JSONSerialization.data(withJSONObject: payload))
        continuations.removeValue(forKey: id)?.resume(returning: WorkerResult(event: event, candidate: candidate, report: report))
    }
    func fail(_ id: UUID, error: Error) { continuations.removeValue(forKey: id)?.resume(throwing: error) }
    var count: Int { starts.count }
}

@MainActor final class QueueTests: XCTestCase {
    private func source(_ root: URL, _ name: String) throws -> URL {
        let url = root.appendingPathComponent(name); try Data(name.utf8).write(to: url); return url
    }
    private func temp() throws -> URL {
        let path = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: path, withIntermediateDirectories: false); return path
    }
    private func eventually(_ predicate: () async -> Bool, file: StaticString = #filePath, line: UInt = #line) async throws {
        for _ in 0..<200 { if await predicate() { return }; try await Task.sleep(nanoseconds: 10_000_000) }
        XCTFail("Timed out awaiting queue state", file: file, line: line)
    }
    func testSequentialNewImportsAndWarningStatus() async throws {
        let root = try temp(); defer { try? FileManager.default.removeItem(at: root) }
        let worker = ControlledWorker(); let queue = JobQueue(store: try SnapshotStore(root: root), worker: worker)
        await queue.add([try source(root, "one.STL")]); try await eventually { await worker.count == 1 }
        await queue.add([try source(root, "日本語 'two'.stl")]); XCTAssertEqual(queue.jobs[1].status, .queued)
        let currentCount = await worker.count; XCTAssertEqual(currentCount, 1)
        try await worker.complete(queue.jobs[0].id, warnings: true)
        try await eventually { await worker.count == 2 }
        try await worker.complete(queue.jobs[1].id)
        try await eventually { queue.jobs[1].status == .unchanged }
        XCTAssertEqual(queue.jobs[0].status, .review); XCTAssertEqual(queue.jobs[0].warnings, ["Review geometry"])
        let maximum = await worker.maximumSimultaneous; XCTAssertEqual(maximum, 1)
        XCTAssertTrue(queue.readyIDs.isEmpty); await queue.shutdown()
    }
    func testCanceledCompletionCannotResurrectAndNextRuns() async throws {
        let root = try temp(); defer { try? FileManager.default.removeItem(at: root) }
        let worker = ControlledWorker(); let queue = JobQueue(store: try SnapshotStore(root: root), worker: worker)
        await queue.add([try source(root, "one.stl"), try source(root, "two.stl")])
        try await eventually { await worker.count == 1 }
        let first = queue.jobs[0].id; queue.cancel(first)
        try await worker.complete(first)
        try await eventually { await worker.count == 2 }
        XCTAssertEqual(queue.jobs[0].status, .canceled)
        await worker.fail(queue.jobs[1].id, error: WorkerFailure.timeout)
        try await eventually { queue.jobs[1].status == .incomplete }
        XCTAssertTrue(queue.readyIDs.isEmpty); await queue.shutdown()
    }
    func testQueuedCancellationDuplicatesAndMixedInput() async throws {
        let root = try temp(); defer { try? FileManager.default.removeItem(at: root) }
        let worker = ControlledWorker(); let queue = JobQueue(store: try SnapshotStore(root: root), worker: worker)
        let first = try source(root, "first.stl")
        await queue.add([first, first, try source(root, "bad.zip"), try source(root, "second.stl")])
        try await eventually { await worker.count == 1 }
        XCTAssertEqual(queue.jobs.count, 2); XCTAssertEqual(queue.inputMessages.count, 2)
        queue.cancel(queue.jobs[1].id)
        await worker.fail(queue.jobs[0].id, error: WorkerFailure.crashed("synthetic"))
        try await eventually { queue.jobs[0].status == .error }
        XCTAssertEqual(queue.jobs[1].status, .canceled)
        let count = await worker.count; XCTAssertEqual(count, 1)
        queue.clearFinished(); XCTAssertTrue(queue.jobs.isEmpty); await queue.shutdown()
    }
    func testPartialBatchAndSaveFailureRetainsVerifiedCandidate() async throws {
        let root = try temp(); defer { try? FileManager.default.removeItem(at: root) }
        let worker = ControlledWorker()
        let exporter = Exporter { phase, url in
            if phase == .stageWritten, String(decoding: try Data(contentsOf: url), as: UTF8.self).contains("first") {
                throw LocalFileError.system("Injected disk full", ENOSPC)
            }
        }
        let queue = JobQueue(store: try SnapshotStore(root: root), worker: worker, exporter: exporter)
        await queue.add([try source(root, "first.stl"), try source(root, "second.stl")])
        for index in 0..<2 {
            try await eventually { await worker.count == index + 1 }
            let item = queue.jobs[index]
            let candidate = VerifiedArtifact(url: item.snapshot.input, sha256: item.snapshot.sha256,
                                             byteSize: try Data(contentsOf: item.snapshot.input).count)
            try await worker.complete(item.id, outcome: "repaired", warnings: true, candidate: candidate)
            try await eventually { queue.jobs[index].status == .ready }
        }
        await queue.save(queue.readyIDs, to: root)
        XCTAssertEqual(queue.jobs[0].status, .ready)
        XCTAssertTrue(queue.jobs[0].message.contains("Save failed"))
        XCTAssertEqual(queue.jobs[1].status, .saved)
        XCTAssertNotNil(queue.jobs[1].savedURL)
        XCTAssertEqual(queue.readyIDs, [queue.jobs[0].id])
        await queue.shutdown()
    }

    func testShutdownWaitsForActiveSaveAndPreservesPublishedFile() async throws {
        let root = try temp(); defer { try? FileManager.default.removeItem(at: root) }
        let worker = ControlledWorker()
        let exporter = Exporter { phase, _ in if phase == .stageWritten { Thread.sleep(forTimeInterval: 0.2) } }
        let queue = JobQueue(store: try SnapshotStore(root: root), worker: worker, exporter: exporter)
        await queue.add([try source(root, "part.stl")])
        try await eventually { await worker.count == 1 }
        let item = queue.jobs[0]
        let candidate = VerifiedArtifact(url: item.snapshot.input, sha256: item.snapshot.sha256,
                                         byteSize: try Data(contentsOf: item.snapshot.input).count)
        try await worker.complete(item.id, outcome: "repaired", candidate: candidate)
        try await eventually { queue.jobs[0].status == .ready }
        let saving = Task { await queue.save([item.id], to: root) }
        try await eventually { queue.jobs[0].status == .saving }
        await queue.shutdown(); await saving.value
        XCTAssertEqual(queue.jobs[0].status, .saved)
        let saved = try XCTUnwrap(queue.jobs[0].savedURL)
        XCTAssertTrue(FileManager.default.fileExists(atPath: saved.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: item.snapshot.directory.path))
    }

    func testAdvancedToleranceSharedByDefaultImport() async throws {
        let root = try temp(); defer { try? FileManager.default.removeItem(at: root) }
        let worker = ControlledWorker(); let queue = JobQueue(store: try SnapshotStore(root: root), worker: worker)
        queue.mergeTinyEdges = true; queue.toleranceText = "0.00001"
        await queue.add([try source(root, "part.stl")])
        XCTAssertEqual(queue.jobs[0].tolerance, 0.00001)
        try await eventually { await worker.count == 1 }
        try await worker.complete(queue.jobs[0].id)
        try await eventually { queue.jobs[0].status == .unchanged }
        await queue.shutdown()
    }

    func testCanceledRowClearWaitsForWorkerBeforeDeletingSnapshot() async throws {
        let root = try temp(); defer { try? FileManager.default.removeItem(at: root) }
        let worker = ControlledWorker(); let queue = JobQueue(store: try SnapshotStore(root: root), worker: worker)
        await queue.add([try source(root, "part.stl")])
        try await eventually { await worker.count == 1 }
        let item = queue.jobs[0]; queue.cancel(item.id); queue.clearFinished()
        XCTAssertTrue(queue.jobs.isEmpty)
        XCTAssertTrue(FileManager.default.fileExists(atPath: item.snapshot.directory.path))
        try await worker.complete(item.id)
        try await eventually { !FileManager.default.fileExists(atPath: item.snapshot.directory.path) }
        await queue.shutdown()
    }

    func testCompletedRefusalRetainsExportableReportWithoutSaveCandidate() async throws {
        let root = try temp(); defer { try? FileManager.default.removeItem(at: root) }
        let worker = ControlledWorker(); let queue = JobQueue(store: try SnapshotStore(root: root), worker: worker)
        await queue.add([try source(root, "part.stl")])
        try await eventually { await worker.count == 1 }
        let item = queue.jobs[0]
        let reportURL = item.snapshot.directory.appendingPathComponent("report.json")
        let bytes = Data("{\"error\":\"unsupported geometry\"}".utf8)
        try bytes.write(to: reportURL)
        let report = VerifiedArtifact(url: reportURL, sha256: SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined(), byteSize: bytes.count)
        try await worker.complete(item.id, outcome: "refused", report: report)
        try await eventually { queue.jobs[0].status == .refused }
        XCTAssertTrue(queue.readyIDs.isEmpty)
        await queue.exportReport(item.id, to: root)
        XCTAssertTrue(FileManager.default.fileExists(atPath: root.appendingPathComponent("part-report.json").path))
        await queue.shutdown()
    }

    func testEveryNonReadyStatusDisablesSave() {
        for status in JobStatus.allCases { XCTAssertEqual(status.canSave, status == .ready) }
    }
    func testInvalidToleranceDoesNotQueue() async throws {
        let root = try temp(); defer { try? FileManager.default.removeItem(at: root) }
        let queue = JobQueue(store: try SnapshotStore(root: root), worker: ControlledWorker())
        let url = try source(root, "one.stl")
        for tolerance in [Double.nan, .infinity, -1, 2] { await queue.add([url], tolerance: tolerance) }
        XCTAssertTrue(queue.jobs.isEmpty); XCTAssertEqual(queue.inputMessages.count, 4); await queue.shutdown()
    }
}
