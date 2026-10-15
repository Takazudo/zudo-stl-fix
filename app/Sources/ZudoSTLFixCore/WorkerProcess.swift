import Foundation
import Darwin

private final class CancellationFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var value = false
    func cancel() { lock.lock(); value = true; lock.unlock() }
    var canceled: Bool { lock.lock(); defer { lock.unlock() }; return value }
}

public struct ProcessWorker: WorkerServing {
    public let executable: URL
    public let arguments: [String]
    public let timeout: TimeInterval
    public init(executable: URL, arguments: [String] = [], timeout: TimeInterval = 120) {
        self.executable = executable; self.arguments = arguments; self.timeout = timeout
    }
    public static var bundled: ProcessWorker {
        ProcessWorker(executable: Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/STLWorker.app/Contents/MacOS/stl-worker"))
    }
    public func run(snapshot: Snapshot, tolerance: Double, progress: @escaping @Sendable (String) -> Void) async throws -> WorkerResult {
        let flag = CancellationFlag()
        return try await withTaskCancellationHandler(operation: {
            try Task.checkCancellation()
            return try await Task.detached(priority: .userInitiated) {
                try execute(snapshot: snapshot, tolerance: tolerance, flag: flag, progress: progress)
            }.value
        }, onCancel: { flag.cancel() })
    }
    private func execute(snapshot: Snapshot, tolerance: Double, flag: CancellationFlag, progress: @escaping @Sendable (String) -> Void) throws -> WorkerResult {
        guard tolerance.isFinite, tolerance >= 0, tolerance <= 1 else { throw WorkerFailure.protocolError("Invalid existing-edge tolerance") }
        let request: [String: Any] = ["protocol_version": 1, "job_id": snapshot.id.uuidString,
            "operation": "check_and_repair", "input_path": snapshot.input.path, "staging_directory": snapshot.directory.path,
            "options": ["weld_tolerance": tolerance, "max_faces": 20000, "max_pairs": 2000000]]
        var data = try JSONSerialization.data(withJSONObject: request); data.append(10)
        guard data.count < 4096 else { throw WorkerFailure.protocolError("Request paths too long") }
        let process = Process(); process.executableURL = executable; process.arguments = arguments
        process.currentDirectoryURL = snapshot.directory
        // Explicit minimal environment: no user Python configuration or runtime downloads.
        process.environment = ["PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "PYTHONNOUSERSITE": "1"]
        let input = Pipe(), output = Pipe(), errors = Pipe()
        process.standardInput = input; process.standardOutput = output; process.standardError = errors
        try process.run()
        let outFD = output.fileHandleForReading.fileDescriptor
        let errFD = errors.fileHandleForReading.fileDescriptor
        defer {
            try? input.fileHandleForWriting.close(); try? output.fileHandleForReading.close(); try? errors.fileHandleForReading.close()
            if process.isRunning { kill(process.processIdentifier, SIGKILL); process.waitUntilExit() }
        }
        guard fcntl(outFD, F_SETFL, O_NONBLOCK) == 0,
              fcntl(errFD, F_SETFL, O_NONBLOCK) == 0,
              fcntl(input.fileHandleForWriting.fileDescriptor, F_SETNOSIGPIPE, 1) == 0 else {
            throw WorkerFailure.protocolError("Cannot configure safe process pipes")
        }
        try input.fileHandleForWriting.write(contentsOf: data); try input.fileHandleForWriting.close()
        var parser = WorkerProtocolParser(jobID: snapshot.id)
        var failure: Error?
        var termAt: TimeInterval?
        let start = ProcessInfo.processInfo.systemUptime
        var exitAt: TimeInterval?
        var outEOF = false, errEOF = false
        var stderrCount = 0
        var buffer = [UInt8](repeating: 0, count: 16384)
        while true {
            let now = ProcessInfo.processInfo.systemUptime
            if flag.canceled { failure = WorkerFailure.canceled }
            else if now - start >= timeout, failure == nil { failure = WorkerFailure.timeout }
            if failure != nil, termAt == nil { termAt = now; if process.isRunning { process.terminate() } }
            if let termAt, now - termAt >= 2, process.isRunning { kill(process.processIdentifier, SIGKILL) }
            for (fd, isOutput) in [(outFD, true), (errFD, false)] {
                // A bounded amount per cycle prevents stdout floods starving cancellation.
                for _ in 0..<8 {
                    let amount = read(fd, &buffer, buffer.count)
                    if amount == 0 { if isOutput { outEOF = true } else { errEOF = true }; break }
                    if amount < 0 {
                        if errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR { failure = WorkerFailure.protocolError("Pipe read failure") }
                        break
                    }
                    if isOutput, failure == nil {
                        do { for event in try parser.append(Data(buffer.prefix(amount))) { if let phase = event.phase { progress(phase) } } }
                        catch { failure = error }
                    } else if !isOutput {
                        stderrCount += amount
                        if stderrCount > 1024 * 1024, failure == nil { failure = WorkerFailure.protocolError("Excessive stderr") }
                    }
                }
            }
            if !process.isRunning {
                if exitAt == nil { exitAt = now }
                if outEOF && errEOF { break }
                // Even inherited pipe handles cannot keep a dead worker alive indefinitely.
                if now - (exitAt ?? now) > 2 { failure = failure ?? WorkerFailure.protocolError("Pipes remained open after exit"); break }
            }
            usleep(10_000)
        }
        process.waitUntilExit()
        if flag.canceled { throw WorkerFailure.canceled }
        if let failure { throw failure }
        let terminal = try parser.finish(exitStatus: process.terminationStatus, exitedNormally: process.terminationReason == .exit)
        let candidate = try terminal.candidate?.verified(in: snapshot.directory)
        let report = try terminal.report?.verified(in: snapshot.directory, maximum: 16 * 1024 * 1024)
        // Verify the private input was not altered by a worker before accepting its result.
        let inputSize = try snapshot.input.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        try FileVerification.verify(VerifiedArtifact(url: snapshot.input, sha256: snapshot.sha256, byteSize: inputSize))
        if flag.canceled { throw WorkerFailure.canceled }
        if ProcessInfo.processInfo.systemUptime - start >= timeout { throw WorkerFailure.timeout }
        return WorkerResult(event: terminal, candidate: candidate, report: report)
    }
}
