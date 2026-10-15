import Foundation
import CryptoKit
import Darwin

public enum LocalFileError: Error, LocalizedError, Sendable {
    case invalidInput(String), inputChanged, verificationFailed, system(String, Int32), collisions
    public var errorDescription: String? {
        switch self {
        case .invalidInput(let reason): return reason
        case .inputChanged: return "The input changed while it was being copied. Add it again."
        case .verificationFailed: return "The stored file does not match the verified candidate."
        case .system(let operation, let code): return "\(operation): \(String(cString: strerror(code)))"
        case .collisions: return "Could not find an available output name."
        }
    }
}

public struct Snapshot: Sendable {
    public let id: UUID
    public let directory: URL
    public let input: URL
    public let original: URL
    public let identity: String
    public let sha256: String
}

public struct VerifiedArtifact: Sendable {
    public let url: URL
    public let sha256: String
    public let byteSize: Int
    public init(url: URL, sha256: String, byteSize: Int) {
        self.url = url; self.sha256 = sha256; self.byteSize = byteSize
    }
}

private let maximumBytes = 64 * 1024 * 1024
private func failure(_ operation: String) -> LocalFileError { .system(operation, errno) }
// Foundation's resolvingSymlinksInPath strips a leading /private, yielding /var or /tmp
// symlink paths that the worker rightly rejects; realpath(3) keeps the physical path.
func physicalDirectory(_ url: URL) throws -> URL {
    guard let resolved = realpath(url.path, nil) else { throw failure("Resolve folder") }
    defer { free(resolved) }
    return URL(fileURLWithPath: String(cString: resolved), isDirectory: true)
}
private func metadata(_ fd: Int32) throws -> stat {
    var value = stat()
    guard fstat(fd, &value) == 0 else { throw failure("Inspect file") }
    return value
}
private func regular(_ value: stat) -> Bool { value.st_mode & mode_t(S_IFMT) == mode_t(S_IFREG) }
private func sameIdentity(_ a: stat, _ b: stat) -> Bool { a.st_dev == b.st_dev && a.st_ino == b.st_ino }
private func unchanged(_ a: stat, _ b: stat) -> Bool {
    sameIdentity(a, b) && a.st_size == b.st_size &&
    a.st_mtimespec.tv_sec == b.st_mtimespec.tv_sec && a.st_mtimespec.tv_nsec == b.st_mtimespec.tv_nsec &&
    a.st_ctimespec.tv_sec == b.st_ctimespec.tv_sec && a.st_ctimespec.tv_nsec == b.st_ctimespec.tv_nsec
}
private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
private func readBounded(_ fd: Int32, limit: Int = maximumBytes) throws -> Data {
    var bytes = Data()
    var buffer = [UInt8](repeating: 0, count: 64 * 1024)
    while true {
        let count = Darwin.read(fd, &buffer, buffer.count)
        if count < 0 { if errno == EINTR { continue }; throw failure("Read file") }
        if count == 0 { return bytes }
        guard bytes.count <= limit - count else { throw LocalFileError.invalidInput("Files larger than 64 MiB are unsupported.") }
        bytes.append(contentsOf: buffer.prefix(count))
    }
}
private func writeAll(_ data: Data, fd: Int32) throws {
    try data.withUnsafeBytes { bytes in
        var offset = 0
        while offset < bytes.count {
            let count = Darwin.write(fd, bytes.baseAddress!.advanced(by: offset), bytes.count - offset)
            if count < 0 { if errno == EINTR { continue }; throw failure("Write file") }
            guard count > 0 else { throw LocalFileError.system("Write file", EIO) }
            offset += count
        }
    }
    guard fsync(fd) == 0 else { throw failure("Flush file") }
}
private func openRegular(_ url: URL) throws -> Int32 {
    guard url.isFileURL, url.host == nil || url.host == "" || url.host == "localhost" else {
        throw LocalFileError.invalidInput("Choose a local file.")
    }
    let fd = open(url.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
    guard fd >= 0 else { throw failure("Open file") }
    do {
        let info = try metadata(fd)
        guard regular(info), info.st_size >= 0, info.st_size <= maximumBytes else {
            throw LocalFileError.invalidInput("Choose a regular local file of at most 64 MiB.")
        }
        return fd
    } catch { close(fd); throw error }
}

public enum FileVerification {
    /// Reads through one descriptor and checks it did not change during verification.
    public static func verify(_ artifact: VerifiedArtifact) throws {
        _ = try checkedBytes(artifact)
    }
    fileprivate static func checkedBytes(_ artifact: VerifiedArtifact) throws -> Data {
        guard artifact.byteSize >= 0, artifact.byteSize <= maximumBytes,
              artifact.sha256.count == 64,
              artifact.sha256.allSatisfy({ $0.isASCII && ("0123456789abcdef".contains($0)) }) else {
            throw LocalFileError.verificationFailed
        }
        let fd = try openRegular(artifact.url)
        defer { close(fd) }
        let before = try metadata(fd)
        let bytes = try readBounded(fd)
        guard unchanged(before, try metadata(fd)), bytes.count == artifact.byteSize,
              digest(bytes) == artifact.sha256 else { throw LocalFileError.verificationFailed }
        return bytes
    }
}

private struct RootOwnership: Codable {
    let magic: String
    let version: Int
    let rootID: UUID
    let device: Int64
    let inode: UInt64
    let uid: UInt32
    static let identifier = "com.takazudo.zudostlfix.private-snapshots"
    static let filename = ".owner.lock"
    static let prefix = "zudo-stl-fix-"
}

/// The open file description owns the advisory lock, including across actor calls.
/// Closing it on normal deallocation or process death makes crash remnants reclaimable.
private final class RootLease: @unchecked Sendable {
    let fd: Int32
    let rootIdentity: stat
    init(fd: Int32, rootIdentity: stat) { self.fd = fd; self.rootIdentity = rootIdentity }
    deinit { close(fd) }
}

private func createRootLease(root: URL, id: UUID) throws -> RootLease {
    let dirFD = open(root.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
    guard dirFD >= 0 else { throw failure("Open snapshot folder") }
    defer { close(dirFD) }
    let info = try metadata(dirFD)
    let fd = openat(dirFD, RootOwnership.filename, O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
    guard fd >= 0 else { throw failure("Create snapshot ownership marker") }
    do {
        guard flock(fd, LOCK_EX | LOCK_NB) == 0 else { throw failure("Lock snapshot folder") }
        let marker = RootOwnership(magic: RootOwnership.identifier, version: 1, rootID: id,
                                   device: Int64(info.st_dev), inode: UInt64(info.st_ino), uid: getuid())
        try writeAll(JSONEncoder().encode(marker), fd: fd)
        return RootLease(fd: fd, rootIdentity: info)
    } catch { close(fd); throw error }
}

/// Best-effort crash cleanup. Prefix alone never establishes ownership. A stale root
/// must have the exact marker schema bound to its uid, UUID, device and inode, private
/// permissions, and an unlocked regular marker. Live instances are left untouched.
private func reapStaleRoots(parent: URL) {
    guard let roots = try? FileManager.default.contentsOfDirectory(at: parent, includingPropertiesForKeys: nil) else { return }
    for root in roots {
        let name = root.lastPathComponent
        guard name.hasPrefix(RootOwnership.prefix),
              let id = UUID(uuidString: String(name.dropFirst(RootOwnership.prefix.count))) else { continue }
        let dirFD = open(root.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard dirFD >= 0 else { continue }
        defer { close(dirFD) }
        guard let info = try? metadata(dirFD), info.st_uid == getuid(),
              info.st_mode & 0o777 == 0o700 else { continue }
        let fd = openat(dirFD, RootOwnership.filename, O_RDWR | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
        guard fd >= 0 else { continue }
        defer { close(fd) }
        guard let lockInfo = try? metadata(fd), regular(lockInfo), lockInfo.st_uid == getuid(),
              lockInfo.st_mode & 0o777 == 0o600, lockInfo.st_nlink == 1,
              lockInfo.st_size > 0, lockInfo.st_size <= 4096,
              flock(fd, LOCK_EX | LOCK_NB) == 0,
              let bytes = try? readBounded(fd, limit: 4096),
              let marker = try? JSONDecoder().decode(RootOwnership.self, from: bytes),
              marker.magic == RootOwnership.identifier, marker.version == 1, marker.rootID == id,
              marker.uid == getuid(), marker.device == Int64(info.st_dev), marker.inode == UInt64(info.st_ino)
        else { continue }
        var currentRoot = stat(), currentMarker = stat()
        guard lstat(root.path, &currentRoot) == 0, sameIdentity(currentRoot, info),
              fstatat(dirFD, RootOwnership.filename, &currentMarker, AT_SYMLINK_NOFOLLOW) == 0,
              unchanged(currentMarker, lockInfo) else { continue }
        // removeItem removes descendant symlinks themselves; it does not traverse them.
        // No arbitrary user path or directory identified only by its prefix is removed.
        try? FileManager.default.removeItem(at: root)
    }
}

/// Actor isolation keeps snapshot reads and writes off the main actor.
public actor SnapshotStore {
    public let root: URL
    private var owned: [UUID: URL] = [:]
    private let afterRead: (@Sendable (URL) throws -> Void)?
    private let lease: RootLease
    public init(root: URL? = nil, afterRead: (@Sendable (URL) throws -> Void)? = nil) throws {
        // Always create a new owned child, even when a caller supplies a parent.
        let parent = try physicalDirectory(root ?? FileManager.default.temporaryDirectory)
        reapStaleRoots(parent: parent)
        let id = UUID()
        let newRoot = parent.appendingPathComponent("\(RootOwnership.prefix)\(id.uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: newRoot, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        do { self.lease = try createRootLease(root: newRoot, id: id) }
        catch { try? FileManager.default.removeItem(at: newRoot); throw error }
        self.root = newRoot
        self.afterRead = afterRead
    }
    public func snapshot(_ url: URL) throws -> Snapshot {
        guard url.isFileURL, url.host == nil || url.host == "" || url.host == "localhost",
              url.pathExtension.lowercased() == "stl" else {
            throw LocalFileError.invalidInput("Choose a local STL file.")
        }
        let values = try url.resourceValues(forKeys: [.isAliasFileKey, .isSymbolicLinkKey, .volumeIsLocalKey])
        guard values.isAliasFile != true, values.isSymbolicLink != true, values.volumeIsLocal == true else {
            throw LocalFileError.invalidInput("Aliases, symbolic links, and remote files are unsupported.")
        }
        let source = try openRegular(url)
        defer { close(source) }
        let before = try metadata(source)
        let bytes = try readBounded(source)
        try afterRead?(url)
        var current = stat()
        guard lstat(url.path, &current) == 0, unchanged(before, current),
              unchanged(before, try metadata(source)), bytes.count == Int(before.st_size) else {
            throw LocalFileError.inputChanged
        }
        let id = UUID()
        let directory = root.appendingPathComponent(id.uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        do {
            let input = directory.appendingPathComponent("input.stl")
            let fd = open(input.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o400)
            guard fd >= 0 else { throw failure("Create snapshot") }
            do { try writeAll(bytes, fd: fd); close(fd) } catch { close(fd); throw error }
            let hash = digest(bytes)
            try FileVerification.verify(VerifiedArtifact(url: input, sha256: hash, byteSize: bytes.count))
            owned[id] = directory
            return Snapshot(id: id, directory: directory, input: input, original: url,
                            identity: "\(before.st_dev):\(before.st_ino)", sha256: hash)
        } catch { try? FileManager.default.removeItem(at: directory); throw error }
    }
    public func remove(_ snapshot: Snapshot) throws {
        guard let directory = owned[snapshot.id], directory == snapshot.directory else { return }
        try FileManager.default.removeItem(at: directory)
        owned.removeValue(forKey: snapshot.id)
    }
    public func cleanup() throws {
        // This root is a uniquely created app-owned directory, never a caller's parent.
        var current = stat()
        if lstat(root.path, &current) == 0 {
            guard sameIdentity(current, lease.rootIdentity) else { throw LocalFileError.verificationFailed }
            try FileManager.default.removeItem(at: root)
        } else if errno != ENOENT { throw failure("Inspect snapshot folder") }
        owned.removeAll()
    }
}

public actor Exporter {
    public enum Checkpoint: Sendable { case stageWritten, beforePublication, afterPublication }
    public typealias Hook = @Sendable (Checkpoint, URL) throws -> Void
    private let hook: Hook?
    public init(hook: Hook? = nil) { self.hook = hook }

    public func save(candidate: VerifiedArtifact, stem: String, directory: URL,
                     protectedInputs: [URL]) throws -> URL {
        try publish(candidate: candidate, stem: stem, directory: directory,
                    protectedInputs: protectedInputs, label: "fixed", fileExtension: "stl")
    }

    public func exportReport(candidate: VerifiedArtifact, stem: String, directory: URL,
                             protectedInputs: [URL]) throws -> URL {
        try publish(candidate: candidate, stem: stem, directory: directory,
                    protectedInputs: protectedInputs, label: "report", fileExtension: "json")
    }

    private func publish(candidate: VerifiedArtifact, stem: String, directory: URL,
                         protectedInputs: [URL], label: String, fileExtension: String) throws -> URL {
        guard directory.isFileURL, directory.host == nil || directory.host == "" || directory.host == "localhost",
              !stem.isEmpty, !stem.contains("/"), !stem.contains("\0") else {
            throw LocalFileError.invalidInput("Choose a local output folder and valid filename.")
        }
        let folder = try physicalDirectory(directory)
        let resource = try folder.resourceValues(forKeys: [.isAliasFileKey, .volumeIsLocalKey])
        guard resource.isAliasFile != true, resource.volumeIsLocal == true else {
            throw LocalFileError.invalidInput("Choose a local output folder.")
        }
        let dirFD = open(folder.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard dirFD >= 0 else { throw failure("Open output folder") }
        defer { close(dirFD) }
        let folderIdentity = try metadata(dirFD)
        // Defense in depth: an original must never be accepted as a repaired artifact.
        let candidateFD = try openRegular(candidate.url)
        let candidateIdentity: stat
        do { candidateIdentity = try metadata(candidateFD); close(candidateFD) }
        catch { close(candidateFD); throw error }
        for input in protectedInputs {
            var info = stat()
            if stat(input.path, &info) == 0, sameIdentity(info, candidateIdentity) {
                throw LocalFileError.invalidInput("An original input cannot be exported as a repair.")
            }
        }
        let bytes = try FileVerification.checkedBytes(candidate)
        // A private directory on the destination filesystem protects the staging name
        // from other users who can write into a shared output directory.
        let stageDirectory = ".zudo-stl-fix-\(UUID().uuidString).tmp"
        guard mkdirat(dirFD, stageDirectory, 0o700) == 0 else { throw failure("Create private staging folder") }
        let stageDirFD = openat(dirFD, stageDirectory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard stageDirFD >= 0 else {
            // Do not remove a path whose identity could not be established.
            throw failure("Open private staging folder")
        }
        let stageDirectoryIdentity = try metadata(stageDirFD)
        defer {
            close(stageDirFD)
            removeOwned(dirFD: dirFD, name: stageDirectory, identity: stageDirectoryIdentity, directory: true)
        }
        let stage = "candidate"
        let stageURL = folder.appendingPathComponent(stageDirectory, isDirectory: true).appendingPathComponent(stage)
        let fd = openat(stageDirFD, stage, O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw failure("Create output staging file") }
        defer { close(fd) }
        let stageIdentity = try metadata(fd)
        defer { removeOwned(dirFD: stageDirFD, name: stage, identity: stageIdentity) }
        try writeAll(bytes, fd: fd)
        try hook?(.stageWritten, stageURL)
        try verifyDescriptor(fd, candidate: candidate)
        try hook?(.beforePublication, stageURL)
        // Hooks and intervening changes cannot bypass the immediate pre-publication check.
        try verifyDescriptor(fd, candidate: candidate)
        var stageAtPath = stat()
        guard fstatat(stageDirFD, stage, &stageAtPath, AT_SYMLINK_NOFOLLOW) == 0,
              sameIdentity(stageAtPath, stageIdentity) else { throw LocalFileError.verificationFailed }
        for suffix in 1...10_000 {
            let name = "\(stem)-\(label)\(suffix == 1 ? "" : "-\(suffix)").\(fileExtension)"
            let folded = name.folding(options: [.caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            let names = try FileManager.default.contentsOfDirectory(atPath: folder.path)
            if names.contains(where: { $0.folding(options: [.caseInsensitive], locale: Locale(identifier: "en_US_POSIX")) == folded }) { continue }
            // Hard-link publication is atomic and refuses EVERY existing entry, including
            // dangling symlinks, input hard links and names on case-insensitive volumes.
            guard linkat(stageDirFD, stage, dirFD, name, 0) == 0 else {
                if errno == EEXIST { continue }; throw failure("Publish output")
            }
            let output = folder.appendingPathComponent(name)
            do {
                try hook?(.afterPublication, output)
                let finalFD = openat(dirFD, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK)
                guard finalFD >= 0 else { throw failure("Verify saved output") }
                defer { close(finalFD) }
                guard sameIdentity(try metadata(finalFD), stageIdentity) else { throw LocalFileError.verificationFailed }
                try verifyDescriptor(finalFD, candidate: candidate)
                var currentDirectory = stat()
                guard stat(folder.path, &currentDirectory) == 0, sameIdentity(currentDirectory, folderIdentity) else {
                    throw LocalFileError.verificationFailed
                }
                // fsync(file) completed before publication; directory fsync improves durability.
                // Some filesystems do not implement directory fsync; do not claim stronger guarantees.
                if fsync(dirFD) != 0 && errno != EINVAL && errno != ENOTSUP { throw failure("Flush output folder") }
                var finalAtPath = stat()
                guard fstatat(dirFD, name, &finalAtPath, AT_SYMLINK_NOFOLLOW) == 0,
                      sameIdentity(finalAtPath, stageIdentity), unchanged(finalAtPath, try metadata(finalFD)) else {
                    throw LocalFileError.verificationFailed
                }
                return output
            } catch {
                removeOwned(dirFD: dirFD, name: name, identity: stageIdentity)
                throw error
            }
        }
        throw LocalFileError.collisions
    }
}

private func verifyDescriptor(_ fd: Int32, candidate: VerifiedArtifact) throws {
    let before = try metadata(fd)
    guard regular(before), before.st_size == candidate.byteSize, lseek(fd, 0, SEEK_SET) == 0 else {
        throw LocalFileError.verificationFailed
    }
    let bytes = try readBounded(fd)
    guard digest(bytes) == candidate.sha256, unchanged(before, try metadata(fd)) else {
        throw LocalFileError.verificationFailed
    }
}
private func removeOwned(dirFD: Int32, name: String, identity: stat, directory: Bool = false) {
    var actual = stat()
    if fstatat(dirFD, name, &actual, AT_SYMLINK_NOFOLLOW) == 0, sameIdentity(identity, actual) {
        _ = unlinkat(dirFD, name, directory ? AT_REMOVEDIR : 0)
    }
}
