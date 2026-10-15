import Foundation

public enum WorkerFailure: Error, LocalizedError, Sendable {
    case protocolError(String), crashed(String), timeout, canceled, invalidArtifact(String)
    public var errorDescription: String? {
        switch self {
        case .protocolError(let text): return "Worker protocol error: \(text)"
        case .crashed(let text): return "Worker failed: \(text)"
        case .timeout: return "Check incomplete: worker exceeded the time limit."
        case .canceled: return "Canceled"
        case .invalidArtifact(let text): return "Candidate verification failed: \(text)"
        }
    }
}

public enum JSONValue: Codable, Sendable, Equatable {
    case object([String: JSONValue]), array([JSONValue]), string(String), number(Double), bool(Bool), null
    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let value = try? c.decode(Bool.self) { self = .bool(value) }
        else if let value = try? c.decode(Double.self), value.isFinite { self = .number(value) }
        else if let value = try? c.decode(String.self) { self = .string(value) }
        else if let value = try? c.decode([String: JSONValue].self) { self = .object(value) }
        else { self = .array(try c.decode([JSONValue].self)) }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .object(let x): try c.encode(x)
        case .array(let x): try c.encode(x)
        case .string(let x): try c.encode(x)
        case .number(let x): try c.encode(x)
        case .bool(let x): try c.encode(x)
        case .null: try c.encodeNil()
        }
    }
    public var pretty: String {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return (try? String(decoding: encoder.encode(self), as: UTF8.self)) ?? "Unavailable"
    }
}

public struct ArtifactDescriptor: Codable, Sendable {
    public let relative_path: String
    private var path: String { relative_path }
    public let sha256: String
    public let byte_size: Int
    public func verified(in directory: URL, maximum: Int = 64 * 1024 * 1024) throws -> VerifiedArtifact {
        guard !path.isEmpty, !path.hasPrefix("/"), !path.contains("\\"), !path.split(separator: "/").contains(".."),
              path.split(separator: "/").count == 1, byte_size > 0, byte_size <= maximum,
              sha256.count == 64, sha256.allSatisfy({ "0123456789abcdef".contains($0) }) else {
            throw WorkerFailure.invalidArtifact("Invalid artifact descriptor")
        }
        let artifact = VerifiedArtifact(url: directory.appendingPathComponent(path), sha256: sha256, byteSize: byte_size)
        try FileVerification.verify(artifact)
        return artifact
    }
}

public struct WorkerEvent: Decodable, Sendable {
    public let protocol_version: Int
    public let job_id: String
    public let event: String
    public let phase: String?
    public let message: String?
    public let outcome: String?
    public let validation_status: String?
    public let summary: JSONValue?
    public let warnings: [JSONValue]?
    public let candidate: ArtifactDescriptor?
    public let report: ArtifactDescriptor?
    public let error: JSONValue?
}

/// JSONDecoder accepts duplicate object members. Validate every object before
/// decoding so escaped spellings cannot shadow a terminal outcome or artifact.
/// Syntax and UTF-8/string escapes are also checked by JSONDecoder below.
private struct UniqueJSONMembers {
    private let bytes: [UInt8]
    private var index = 0
    init(_ data: Data) { bytes = Array(data) }
    mutating func validate() throws {
        try value(depth: 0); whitespace()
        guard index == bytes.count else { throw invalid() }
    }
    private func invalid() -> WorkerFailure { .protocolError("Malformed JSON or duplicate object member") }
    private mutating func whitespace() {
        while index < bytes.count, [9, 10, 13, 32].contains(bytes[index]) { index += 1 }
    }
    private mutating func take(_ byte: UInt8) throws {
        whitespace(); guard index < bytes.count, bytes[index] == byte else { throw invalid() }; index += 1
    }
    private mutating func string() throws -> String {
        whitespace()
        guard index < bytes.count, bytes[index] == 34 else { throw invalid() }
        let start = index; index += 1
        while index < bytes.count {
            if bytes[index] == 92 {
                index += 2
            } else if bytes[index] == 34 {
                index += 1
                guard let decoded = try? JSONDecoder().decode(String.self, from: Data(bytes[start..<index])) else { throw invalid() }
                return decoded
            } else { index += 1 }
        }
        throw invalid()
    }
    private mutating func value(depth: Int) throws {
        guard depth <= 64 else { throw WorkerFailure.protocolError("Excessive JSON nesting") }
        whitespace(); guard index < bytes.count else { throw invalid() }
        switch bytes[index] {
        case 123: // object
            index += 1; whitespace()
            if index < bytes.count, bytes[index] == 125 { index += 1; return }
            var keys = Set<String>()
            while true {
                let key = try string()
                guard keys.insert(key).inserted else { throw invalid() }
                try take(58); try value(depth: depth + 1); whitespace()
                guard index < bytes.count else { throw invalid() }
                if bytes[index] == 125 { index += 1; return }
                try take(44)
            }
        case 91: // array
            index += 1; whitespace()
            if index < bytes.count, bytes[index] == 93 { index += 1; return }
            while true {
                try value(depth: depth + 1); whitespace()
                guard index < bytes.count else { throw invalid() }
                if bytes[index] == 93 { index += 1; return }
                try take(44)
            }
        case 34: _ = try string()
        default:
            let start = index
            while index < bytes.count, ![9, 10, 13, 32, 44, 93, 125, 58].contains(bytes[index]) { index += 1 }
            guard index > start else { throw invalid() }
            // Number / boolean / null syntax is checked by the final JSONDecoder.
        }
    }
}

/// A strict, bounded stream: exactly one started event, ordered progress, one terminal,
/// a trailing newline, and successful process termination are all required.
public struct WorkerProtocolParser {
    public static let maximumLine = 256 * 1024
    public static let maximumStream = 4 * 1024 * 1024
    private var pending = Data()
    private var total = 0
    private var count = 0
    private var started = false
    private var phaseRank = 0
    private var terminal: WorkerEvent?
    private let jobID: String
    public init(jobID: UUID) { self.jobID = jobID.uuidString }
    public mutating func append(_ chunk: Data) throws -> [WorkerEvent] {
        total += chunk.count
        guard total <= Self.maximumStream else { throw WorkerFailure.protocolError("Excessive stdout") }
        pending.append(chunk)
        var events: [WorkerEvent] = []
        while let end = pending.firstIndex(of: 10) {
            let line = Data(pending[..<end]); pending.removeSubrange(...end)
            guard !line.isEmpty, line.count <= Self.maximumLine else { throw WorkerFailure.protocolError("Invalid line length") }
            count += 1
            guard count <= 512, terminal == nil else { throw WorkerFailure.protocolError("Extra event after result or too many events") }
            var uniqueMembers = UniqueJSONMembers(line)
            try uniqueMembers.validate()
            let value: WorkerEvent
            do { value = try JSONDecoder().decode(WorkerEvent.self, from: line) }
            catch { throw WorkerFailure.protocolError("Malformed JSON event") }
            guard value.protocol_version == 1, value.job_id == jobID else { throw WorkerFailure.protocolError("Wrong job or protocol version") }
            switch value.event {
            case "started":
                guard !started else { throw WorkerFailure.protocolError("Duplicate started event") }; started = true
            case "progress":
                guard started, let phase = value.phase, ["checking", "repairing", "verifying"].contains(phase) else { throw WorkerFailure.protocolError("Invalid progress") }
                let rank = ["checking": 1, "repairing": 2, "verifying": 3][phase]!
                guard rank >= phaseRank else { throw WorkerFailure.protocolError("Regressing progress phase") }
                phaseRank = rank
            case "result":
                guard started, let outcome = value.outcome,
                      ["unchanged", "repaired", "refused", "incomplete", "error"].contains(outcome), value.summary != nil, value.warnings != nil else {
                    throw WorkerFailure.protocolError("Incomplete result")
                }
                if ["unchanged", "repaired"].contains(outcome) {
                    guard ["PASS", "PASS_WITH_WARNINGS"].contains(value.validation_status ?? "") else { throw WorkerFailure.protocolError("Result lacks successful complete validation") }
                }
                if ["unchanged", "repaired"].contains(outcome) {
                    guard case .object(let summary)? = value.summary,
                          case .object(let audit)? = summary["after"],
                          case .array(let failures)? = audit["failures"], failures.isEmpty,
                          case .object(let intersections)? = audit["surface_intersections"],
                          intersections["complete"] == .bool(true),
                          intersections["defect_pair_count"] == .number(0) else {
                        throw WorkerFailure.protocolError("Successful result lacks complete clean audit")
                    }
                    if outcome == "repaired" {
                        guard case .string(let hash)? = audit["sha256"], hash == value.candidate?.sha256 else {
                            throw WorkerFailure.protocolError("Candidate hash differs from serialized audit")
                        }
                    }
                }
                guard (outcome == "repaired") == (value.candidate != nil) else { throw WorkerFailure.protocolError("Candidate/outcome mismatch") }
                terminal = value
            default: throw WorkerFailure.protocolError("Unknown event")
            }
            events.append(value)
        }
        guard pending.count <= Self.maximumLine else { throw WorkerFailure.protocolError("Unterminated oversized line") }
        return events
    }
    public func finish(exitStatus: Int32, exitedNormally: Bool) throws -> WorkerEvent {
        guard pending.isEmpty, let terminal else { throw WorkerFailure.protocolError("Truncated stream or missing result") }
        if terminal.outcome == "error" {
            throw WorkerFailure.crashed(terminal.error?.pretty ?? "Operational error (exit \(exitStatus))")
        }
        guard exitedNormally, exitStatus == 0 else { throw WorkerFailure.crashed("Abnormal exit \(exitStatus)") }
        return terminal
    }
}

public struct WorkerResult: Sendable {
    public let event: WorkerEvent
    public let candidate: VerifiedArtifact?
    public let report: VerifiedArtifact?
}

public protocol WorkerServing: Sendable {
    func run(snapshot: Snapshot, tolerance: Double, progress: @escaping @Sendable (String) -> Void) async throws -> WorkerResult
}
