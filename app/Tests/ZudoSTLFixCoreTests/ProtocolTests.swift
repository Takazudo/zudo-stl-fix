import Foundation
import XCTest
@testable import ZudoSTLFixCore

final class ProtocolTests: XCTestCase {
    private let job = UUID()

    private func event(_ kind: String, fields: [String: Any] = [:], jobID: UUID? = nil, version: Int = 1) throws -> Data {
        var object: [String: Any] = ["event": kind, "job_id": (jobID ?? job).uuidString, "protocol_version": version]
        object.merge(fields) { _, value in value }
        var bytes = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        bytes.append(10)
        return bytes
    }

    private func result(_ outcome: String = "unchanged", fields: [String: Any] = [:]) throws -> Data {
        var values: [String: Any] = ["outcome": outcome, "validation_status": "PASS", "summary": ["after": ["failures": [String](), "surface_intersections": ["complete": true, "defect_pair_count": 0]]], "warnings": [String]()]
        values.merge(fields) { _, value in value }
        return try event("result", fields: values)
    }

    func testByteByByteFragmentationAndCoalescing() throws {
        let stream = try event("started") + event("progress", fields: ["phase": "checking", "message": "Checking 日本語"]) + result()
        var fragmented = WorkerProtocolParser(jobID: job)
        var received: [String] = []
        for byte in stream { received += try fragmented.append(Data([byte])).map(\.event) }
        XCTAssertEqual(received, ["started", "progress", "result"])
        XCTAssertEqual(try fragmented.finish(exitStatus: 0, exitedNormally: true).outcome, "unchanged")
        var coalesced = WorkerProtocolParser(jobID: job)
        XCTAssertEqual(try coalesced.append(stream).map(\.event), received)
        XCTAssertEqual(try coalesced.finish(exitStatus: 0, exitedNormally: true).outcome, "unchanged")
    }

    func testMalformedUnknownWrongJobAndVersionAreRejected() throws {
        let invalid: [Data] = [Data("{\n".utf8), Data([0xff, 10]), Data("\n".utf8),
                               try event("surprise"), try event("started", jobID: UUID()), try event("started", version: 2)]
        for bytes in invalid {
            var parser = WorkerProtocolParser(jobID: job)
            XCTAssertThrowsError(try parser.append(bytes))
        }
    }

    func testStartIsRequiredExactlyOnceAndProgressPhaseIsKnown() throws {
        for bytes in [try result(), try event("progress", fields: ["phase": "checking"]),
                      try event("started") + event("started"),
                      try event("started") + event("progress", fields: ["phase": "unknown"]),
                      try event("started") + event("progress")] {
            var parser = WorkerProtocolParser(jobID: job)
            XCTAssertThrowsError(try parser.append(bytes))
        }
    }

    func testExactlyOneTerminalAndNoEventsAfterTerminal() throws {
        for extra in [try result(), try event("progress", fields: ["phase": "verifying"]), try event("started")] {
            var parser = WorkerProtocolParser(jobID: job)
            _ = try parser.append(event("started") + result())
            XCTAssertThrowsError(try parser.append(extra))
        }
    }

    func testTruncationMissingTerminalAndAbnormalExitsCannotSucceed() throws {
        var truncated = WorkerProtocolParser(jobID: job)
        var terminal = try result(); terminal.removeLast()
        _ = try truncated.append(event("started") + terminal)
        XCTAssertThrowsError(try truncated.finish(exitStatus: 0, exitedNormally: true))
        var missing = WorkerProtocolParser(jobID: job)
        _ = try missing.append(event("started"))
        XCTAssertThrowsError(try missing.finish(exitStatus: 0, exitedNormally: true))
        var complete = WorkerProtocolParser(jobID: job)
        _ = try complete.append(event("started") + result())
        XCTAssertThrowsError(try complete.finish(exitStatus: 1, exitedNormally: true))
        XCTAssertThrowsError(try complete.finish(exitStatus: 0, exitedNormally: false))
    }

    func testSuccessRequiresCompleteValidationAndCandidateAgreement() throws {
        let descriptor: [String: Any] = ["relative_path": "candidate.stl", "sha256": String(repeating: "a", count: 64), "byte_size": 84]
        for bytes in [try result("unchanged", fields: ["validation_status": "INCOMPLETE"]),
                      try result("unchanged", fields: ["validation_status": NSNull()]),
                      try result("repaired"), try result("unchanged", fields: ["candidate": descriptor]),
                      try result("refused", fields: ["candidate": descriptor]),
                      try result("unknown"), try result(fields: ["summary": NSNull()]),
                      try result(fields: ["warnings": NSNull()])] {
            var parser = WorkerProtocolParser(jobID: job)
            XCTAssertThrowsError(try parser.append(event("started") + bytes))
        }
        var repaired = WorkerProtocolParser(jobID: job)
        _ = try repaired.append(event("started") + result("repaired", fields: ["candidate": descriptor, "validation_status": "PASS_WITH_WARNINGS", "warnings": ["tiny triangle"], "summary": ["after": ["failures": [String](), "surface_intersections": ["complete": true, "defect_pair_count": 0], "sha256": String(repeating: "a", count: 64)]]]))
        XCTAssertEqual(try repaired.finish(exitStatus: 0, exitedNormally: true).warnings, [.string("tiny triangle")])
    }

    func testRefusedAndIncompleteRemainDistinctFromSuccessAndErrorThrows() throws {
        for outcome in ["refused", "incomplete"] {
            var parser = WorkerProtocolParser(jobID: job)
            _ = try parser.append(event("started") + result(outcome, fields: ["validation_status": "FAIL"]))
            let terminal = try parser.finish(exitStatus: 0, exitedNormally: true)
            XCTAssertEqual(terminal.outcome, outcome)
            XCTAssertNil(terminal.candidate)
        }
        var parser = WorkerProtocolParser(jobID: job)
        _ = try parser.append(event("started") + result("error", fields: ["error": "Engine failure"]))
        XCTAssertThrowsError(try parser.finish(exitStatus: 0, exitedNormally: true))
    }


    func testProgressCannotRegressButRepeatedAndSkippedPhasesAreValid() throws {
        var parser = WorkerProtocolParser(jobID: job)
        _ = try parser.append(event("started") + event("progress", fields: ["phase": "verifying"]))
        XCTAssertThrowsError(try parser.append(event("progress", fields: ["phase": "checking"])))
        var valid = WorkerProtocolParser(jobID: job)
        _ = try valid.append(event("started") + event("progress", fields: ["phase": "checking"]) + event("progress", fields: ["phase": "checking"]) + event("progress", fields: ["phase": "verifying"]) + result())
        XCTAssertEqual(try valid.finish(exitStatus: 0, exitedNormally: true).outcome, "unchanged")
    }

    func testIncompleteOrDefectiveScanCannotBeCalledSuccessful() throws {
        let summaries: [[String: Any]] = [
            [:],
            ["after": ["failures": [String](), "surface_intersections": ["complete": false, "defect_pair_count": 0]]],
            ["after": ["failures": [String](), "surface_intersections": ["complete": true, "defect_pair_count": 1]]],
            ["after": ["failures": ["boundary edge"], "surface_intersections": ["complete": true, "defect_pair_count": 0]]]
        ]
        for summary in summaries {
            var parser = WorkerProtocolParser(jobID: job)
            XCTAssertThrowsError(try parser.append(event("started") + result(fields: ["summary": summary])))
        }
    }

    func testStructuredOperationalErrorKeepsExplanationWithNonzeroExit() throws {
        var parser = WorkerProtocolParser(jobID: job)
        _ = try parser.append(event("started") + result("error", fields: ["validation_status": NSNull(), "error": ["code": "permission_denied", "message": "Cannot read private snapshot"]]))
        XCTAssertThrowsError(try parser.finish(exitStatus: 1, exitedNormally: true)) { error in
            XCTAssertTrue(error.localizedDescription.contains("Cannot read private snapshot"))
            XCTAssertTrue(error.localizedDescription.contains("permission_denied"))
        }
    }

    func testDuplicateMembersIncludingEscapedAndNestedKeysAreRejected() throws {
        let original = String(decoding: try result(), as: UTF8.self)
        let duplicateOutcomes = original.replacingOccurrences(of: "\"outcome\":\"unchanged\"", with: "\"outcome\":\"refused\",\"outcome\":\"unchanged\"")
        let duplicateStatus = original.replacingOccurrences(of: "\"validation_status\":\"PASS\"", with: "\"validation_status\":\"FAIL\",\"validation_status\":\"PASS\"")
        let duplicateCandidate = original.trimmingCharacters(in: .whitespacesAndNewlines).dropLast() + ",\"candidate\":null,\"candidate\":null}\n"
        let escapedOutcome = original.replacingOccurrences(of: "\"outcome\":\"unchanged\"", with: #""outcome":"refused","outco\u006de":"unchanged""#)
        let nested = original.replacingOccurrences(of: "\"complete\":true", with: #""complete":false,"comple\u0074e":true"#)
        for invalid in [duplicateOutcomes, duplicateStatus, String(duplicateCandidate), escapedOutcome, nested] {
            var parser = WorkerProtocolParser(jobID: job)
            XCTAssertThrowsError(try parser.append(event("started") + Data(invalid.utf8)))
        }
        var unique = WorkerProtocolParser(jobID: job)
        _ = try unique.append(event("started") + result(fields: ["future_unique_field": ["quoted\"key": "escaped \\ value", "array": [["key": 1], ["key": 2]]]]))
        XCTAssertEqual(try unique.finish(exitStatus: 0, exitedNormally: true).outcome, "unchanged")
    }

    func testLineStreamAndEventCountBounds() throws {
        var line = WorkerProtocolParser(jobID: job)
        XCTAssertThrowsError(try line.append(Data(repeating: 32, count: WorkerProtocolParser.maximumLine + 1)))
        var terminatedLine = WorkerProtocolParser(jobID: job)
        XCTAssertThrowsError(try terminatedLine.append(Data(repeating: 32, count: WorkerProtocolParser.maximumLine + 1) + Data([10])))
        var total = WorkerProtocolParser(jobID: job)
        XCTAssertThrowsError(try total.append(Data(repeating: 32, count: WorkerProtocolParser.maximumStream + 1)))
        var count = WorkerProtocolParser(jobID: job)
        _ = try count.append(event("started"))
        let progress = try event("progress", fields: ["phase": "checking"])
        for _ in 0..<511 { _ = try count.append(progress) }
        XCTAssertThrowsError(try count.append(progress))
    }
}
