import Foundation
import XCTest
@testable import ZudoSTLFixCore

final class ProcessTests: XCTestCase {
    private struct Fixture {
        let root: URL
        let snapshot: Snapshot
        let stream: URL
    }

    private func fixture(complete: Bool = true, trailingNewline: Bool = true) async throws -> Fixture {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("zudo-process-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let original = root.appendingPathComponent("part with spaces.stl")
        try Data("solid example\nendsolid example\n".utf8).write(to: original)
        let store = try SnapshotStore(root: root)
        let snapshot = try await store.snapshot(original)
        let stream = root.appendingPathComponent("worker events.ndjson")
        var events: [[String: Any]] = [["protocol_version": 1, "job_id": snapshot.id.uuidString, "event": "started"]]
        if complete {
            events.append(["protocol_version": 1, "job_id": snapshot.id.uuidString, "event": "result", "outcome": "unchanged",
                           "validation_status": "PASS", "summary": ["after": ["failures": [String](), "surface_intersections": ["complete": true, "defect_pair_count": 0]]], "warnings": [String]()])
        }
        var bytes = Data()
        for event in events { bytes.append(try JSONSerialization.data(withJSONObject: event)); bytes.append(10) }
        if !trailingNewline { bytes.removeLast() }
        try bytes.write(to: stream)
        return Fixture(root: root, snapshot: snapshot, stream: stream)
    }

    // The script is fixed test code. Paths are positional Process arguments, never shell interpolation.
    private func worker(_ script: String, fixture: Fixture, timeout: TimeInterval = 5) -> ProcessWorker {
        ProcessWorker(executable: URL(fileURLWithPath: "/bin/sh"), arguments: ["-c", script, "fake-stl-worker", fixture.stream.path], timeout: timeout)
    }

    private func assertFailure(_ worker: ProcessWorker, snapshot: Snapshot, expected: String? = nil,
                               file: StaticString = #filePath, line: UInt = #line) async {
        do {
            _ = try await worker.run(snapshot: snapshot, tolerance: 0, progress: { _ in })
            XCTFail("Worker unexpectedly succeeded", file: file, line: line)
        } catch {
            if let expected { XCTAssertTrue(error.localizedDescription.contains(expected), "Unexpected error: \(error)", file: file, line: line) }
        }
    }

    func testCompletedWorkerProducesResultOnlyAfterNormalExit() async throws {
        let f = try await fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        let result = try await worker("IFS= read -r request; cat \"$1\"", fixture: f).run(snapshot: f.snapshot, tolerance: 0, progress: { _ in })
        XCTAssertEqual(result.event.outcome, "unchanged")
        XCTAssertNil(result.candidate)
    }

    func testTerminalSuccessFollowedByNonzeroExitOrCrashIsRejected() async throws {
        let f = try await fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        await assertFailure(worker("IFS= read -r request; cat \"$1\"; exit 23", fixture: f), snapshot: f.snapshot, expected: "Abnormal exit")
        await assertFailure(worker("IFS= read -r request; cat \"$1\"; kill -KILL $$", fixture: f), snapshot: f.snapshot, expected: "Abnormal exit")
    }

    func testMissingAndTruncatedResultsAreRejected() async throws {
        let missing = try await fixture(complete: false)
        let truncated = try await fixture(trailingNewline: false)
        defer { try? FileManager.default.removeItem(at: missing.root); try? FileManager.default.removeItem(at: truncated.root) }
        for f in [missing, truncated] {
            await assertFailure(worker("IFS= read -r request; cat \"$1\"", fixture: f), snapshot: f.snapshot, expected: "Truncated")
        }
    }

    func testMalformedAndDuplicateTerminalStreamsAreRejected() async throws {
        let f = try await fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        await assertFailure(worker("IFS= read -r request; printf 'broken\\n'", fixture: f), snapshot: f.snapshot, expected: "Malformed")
        await assertFailure(worker("IFS= read -r request; cat \"$1\"; cat \"$1\"", fixture: f), snapshot: f.snapshot, expected: "Extra event")
    }

    func testStderrFloodIsDrainedAndBounded() async throws {
        let f = try await fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        await assertFailure(worker("IFS= read -r request; dd if=/dev/zero bs=65536 count=20 >&2 2>/dev/null; cat \"$1\"", fixture: f), snapshot: f.snapshot, expected: "Excessive stderr")
    }

    func testStdoutFloodIsRejectedWithoutHanging() async throws {
        let f = try await fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        await assertFailure(worker("IFS= read -r request; dd if=/dev/zero bs=65536 count=80 2>/dev/null", fixture: f), snapshot: f.snapshot, expected: "oversized")
    }

    func testTimeoutEscalatesForTermResistantWorker() async throws {
        let f = try await fixture(complete: false); defer { try? FileManager.default.removeItem(at: f.root) }
        let start = ProcessInfo.processInfo.systemUptime
        await assertFailure(worker("trap '' TERM; IFS= read -r request; cat \"$1\"; while :; do :; done", fixture: f, timeout: 0.15), snapshot: f.snapshot, expected: "time limit")
        XCTAssertLessThan(ProcessInfo.processInfo.systemUptime - start, 10)
    }

    func testCancellationEscalatesForTermResistantWorker() async throws {
        let f = try await fixture(complete: false); defer { try? FileManager.default.removeItem(at: f.root) }
        let subject = worker("trap '' TERM; IFS= read -r request; cat \"$1\"; while :; do :; done", fixture: f)
        let task = Task { try await subject.run(snapshot: f.snapshot, tolerance: 0, progress: { _ in }) }
        try await Task.sleep(for: .milliseconds(150))
        let start = ProcessInfo.processInfo.systemUptime
        task.cancel()
        do { _ = try await task.value; XCTFail("Cancellation must not return a result") }
        catch { XCTAssertTrue(error is CancellationError || error.localizedDescription.contains("Canceled")) }
        XCTAssertLessThan(ProcessInfo.processInfo.systemUptime - start, 10)
    }

    func testSuccessfulTerminalDoesNotBypassTimeout() async throws {
        let f = try await fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        await assertFailure(worker("IFS= read -r request; cat \"$1\"; while :; do :; done", fixture: f, timeout: 0.1), snapshot: f.snapshot, expected: "time limit")
    }

    func testWorkerClosingStdinImmediatelyDoesNotKillHostWithSIGPIPE() async throws {
        let f = try await fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        // Multiple launches cover both scheduling orders of a child that exits before reading stdin.
        for _ in 0..<8 { await assertFailure(worker("exec 0<&-; exit 9", fixture: f), snapshot: f.snapshot) }
    }


    func testWorkerCannotReturnSuccessAfterChangingSnapshot() async throws {
        let f = try await fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        let original = try Data(contentsOf: f.snapshot.original)
        await assertFailure(worker("IFS= read -r request; chmod u+w input.stl; printf corrupt > input.stl; cat \"$1\"", fixture: f), snapshot: f.snapshot)
        XCTAssertEqual(try Data(contentsOf: f.snapshot.original), original)
    }

    func testRepairedResultWithMissingStagedArtifactIsRejected() async throws {
        let f = try await fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        let lines = try String(contentsOf: f.stream, encoding: .utf8).split(separator: "\n")
        var terminal = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(lines[1].utf8)) as? [String: Any])
        let hash = String(repeating: "a", count: 64)
        terminal["outcome"] = "repaired"
        terminal["candidate"] = ["relative_path": "candidate.stl", "sha256": hash, "byte_size": 84]
        terminal["summary"] = ["after": ["failures": [String](), "surface_intersections": ["complete": true, "defect_pair_count": 0], "sha256": hash]]
        var bytes = Data(lines[0].utf8); bytes.append(10)
        bytes.append(try JSONSerialization.data(withJSONObject: terminal)); bytes.append(10)
        try bytes.write(to: f.stream)
        await assertFailure(worker("IFS= read -r request; cat \"$1\"", fixture: f), snapshot: f.snapshot)
    }

    func testInvalidToleranceFailsBeforeLaunchingWorker() async throws {
        let f = try await fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        for tolerance in [-1, Double.nan, Double.infinity, 1.1] {
            do {
                _ = try await worker("IFS= read -r request; cat \"$1\"", fixture: f).run(snapshot: f.snapshot, tolerance: tolerance, progress: { _ in })
                XCTFail("Invalid tolerance accepted")
            } catch { XCTAssertTrue(error.localizedDescription.contains("tolerance")) }
        }
    }
}
