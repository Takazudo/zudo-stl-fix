import XCTest
import Foundation
import CryptoKit
import Darwin
@testable import ZudoSTLFixCore

final class FilesTests: XCTestCase {
    private func temporaryDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: false)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }
    private func artifact(in folder: URL, name: String = "candidate.stl", text: String = "verified serialized bytes") throws -> VerifiedArtifact {
        let data = Data(text.utf8)
        let url = folder.appendingPathComponent(name)
        try data.write(to: url)
        let hash = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        return VerifiedArtifact(url: url, sha256: hash, byteSize: data.count)
    }

    func testDefaultStoreRootIsPhysicalPathTheWorkerAccepts() async throws {
        let store = try SnapshotStore()
        let root = await store.root
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        let resolved = try XCTUnwrap(realpath(root.path, nil)); defer { free(resolved) }
        XCTAssertEqual(root.path, String(cString: resolved))
        XCTAssertTrue(root.path.hasPrefix("/private/"), "temporary root lost its /private component: \(root.path)")
    }

    func testPhysicalDirectoryKeepsPrivatePrefixForSymlinkedTmp() throws {
        XCTAssertEqual(try physicalDirectory(URL(fileURLWithPath: "/tmp")).path, "/private/tmp")
    }

    func testSnapshotCopiesUnusualUppercaseNameAndRecordsHardLinkIdentity() async throws {
        let folder = try temporaryDirectory()
        let original = try artifact(in: folder, name: "- 日本語 ' rail.STL")
        let alias = folder.appendingPathComponent("same.stl")
        try FileManager.default.linkItem(at: original.url, to: alias)
        let store = try SnapshotStore(root: folder)
        let first = try await store.snapshot(original.url)
        let second = try await store.snapshot(alias)
        XCTAssertEqual(first.identity, second.identity)
        XCTAssertEqual(first.sha256, original.sha256)
        XCTAssertNotEqual(first.input, original.url)
        XCTAssertNotEqual(first.directory, second.directory)
        XCTAssertEqual(try Data(contentsOf: first.input), Data("verified serialized bytes".utf8))
        try Data("original subsequently changed".utf8).write(to: original.url)
        XCTAssertEqual(try Data(contentsOf: first.input), Data("verified serialized bytes".utf8))
        try await store.remove(first)
        XCTAssertFalse(FileManager.default.fileExists(atPath: first.directory.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: second.directory.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: original.url.path))
        try await store.cleanup()
        XCTAssertTrue(FileManager.default.fileExists(atPath: folder.path))
    }

    func testTemporaryParentSymlinkIsCanonicalizedForWorker() async throws {
        let root = try temporaryDirectory()
        let actual = try temporaryDirectory()
        let link = root.appendingPathComponent("temporary-link")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: actual)
        let source = try artifact(in: actual)
        let store = try SnapshotStore(root: link)
        let snapshot = try await store.snapshot(source.url)
        XCTAssertEqual(snapshot.directory.path, try physicalDirectory(snapshot.directory).path)
        XCTAssertTrue(snapshot.directory.path.hasPrefix(try physicalDirectory(actual).path + "/"))
        XCTAssertEqual(snapshot.input.deletingLastPathComponent().path, snapshot.directory.path)
        try await store.cleanup()
    }

    func testEqualBasenamesAreDistinctIdentities() async throws {
        let a = try temporaryDirectory(), b = try temporaryDirectory()
        let first = try artifact(in: a, name: "part.stl"), second = try artifact(in: b, name: "part.stl")
        let store = try SnapshotStore(root: a)
        let one = try await store.snapshot(first.url), two = try await store.snapshot(second.url)
        XCTAssertNotEqual(one.identity, two.identity)
        try await store.cleanup()
    }

    func testSourceReplacementDuringSnapshotIsRejected() async throws {
        let folder = try temporaryDirectory()
        let original = try artifact(in: folder)
        let store = try SnapshotStore(root: folder, afterRead: { url in
            try Data("replacement".utf8).write(to: url, options: .atomic)
        })
        do { _ = try await store.snapshot(original.url); XCTFail("Accepted changed input") }
        catch LocalFileError.inputChanged {} catch { XCTFail("Unexpected error: \(error)") }
        let root = await store.root
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path), [".owner.lock"])
        try await store.cleanup()
    }

    func testReportUsesVerifiedJSONPublication() async throws {
        let source = try temporaryDirectory(), destination = try temporaryDirectory()
        let report = try artifact(in: source, name: "report.json", text: "{\"warnings\":[]}")
        let saved = try await Exporter().exportReport(candidate: report, stem: "part", directory: destination, protectedInputs: [])
        XCTAssertEqual(saved.lastPathComponent, "part-report.json")
        try FileVerification.verify(VerifiedArtifact(url: saved, sha256: report.sha256, byteSize: report.byteSize))
    }

    func testSnapshotRejectsWrongExtensionFolderRemoteAndSymlink() async throws {
        let folder = try temporaryDirectory()
        let source = try artifact(in: folder)
        let wrong = try artifact(in: folder, name: "part.zip")
        let link = folder.appendingPathComponent("link.stl")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: source.url)
        let directory = folder.appendingPathComponent("folder.stl")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
        let store = try SnapshotStore(root: folder)
        for url in [wrong.url, link, directory, URL(string: "https://example.invalid/file.stl")!] {
            do { _ = try await store.snapshot(url); XCTFail("Accepted invalid input: \(url)") } catch {}
        }
        try await store.cleanup()
    }

    func testOversizeSnapshotIsRejectedBeforeReading() async throws {
        let folder = try temporaryDirectory()
        let url = folder.appendingPathComponent("huge.stl")
        FileManager.default.createFile(atPath: url.path, contents: nil)
        let handle = try FileHandle(forWritingTo: url)
        try handle.truncate(atOffset: 64 * 1024 * 1024 + 1)
        try handle.close()
        let store = try SnapshotStore(root: folder)
        do { _ = try await store.snapshot(url); XCTFail("Accepted oversized file") } catch {}
        try await store.cleanup()
    }

    func testSaveUsesDeterministicCaseInsensitiveSuffixAndPreservesInputLinks() async throws {
        let source = try temporaryDirectory(), destination = try temporaryDirectory()
        let original = try artifact(in: source, name: "original.stl", text: "original")
        let candidate = try artifact(in: source)
        let existing = destination.appendingPathComponent("RAIL-FIXED.STL")
        try FileManager.default.linkItem(at: original.url, to: existing)
        let symlink = destination.appendingPathComponent("rail-fixed-2.stl")
        try FileManager.default.createSymbolicLink(at: symlink, withDestinationURL: original.url)
        let saved = try await Exporter().save(candidate: candidate, stem: "rail", directory: destination, protectedInputs: [original.url])
        XCTAssertEqual(saved.lastPathComponent, "rail-fixed-3.stl")
        try FileVerification.verify(VerifiedArtifact(url: saved, sha256: candidate.sha256, byteSize: candidate.byteSize))
        XCTAssertEqual(try Data(contentsOf: existing), Data("original".utf8))
        XCTAssertEqual(try Data(contentsOf: original.url), Data("original".utf8))
        XCTAssertFalse(try FileManager.default.contentsOfDirectory(atPath: destination.path).contains { $0.hasPrefix(".zudo") })
    }

    func testOriginalHardLinkCannotMasqueradeAsCandidate() async throws {
        let source = try temporaryDirectory(), destination = try temporaryDirectory()
        let original = try artifact(in: source)
        let link = source.appendingPathComponent("alias.stl")
        try FileManager.default.linkItem(at: original.url, to: link)
        let candidate = VerifiedArtifact(url: link, sha256: original.sha256, byteSize: original.byteSize)
        do {
            _ = try await Exporter().save(candidate: candidate, stem: "part", directory: destination, protectedInputs: [original.url])
            XCTFail("Exported an input hard link")
        } catch {}
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: destination.path), [])
    }

    func testBadHashAndSymlinkCandidateFailWithoutOutput() async throws {
        let source = try temporaryDirectory(), destination = try temporaryDirectory()
        let original = try artifact(in: source)
        let link = source.appendingPathComponent("link.stl")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: original.url)
        let candidates = [VerifiedArtifact(url: original.url, sha256: String(repeating: "0", count: 64), byteSize: original.byteSize),
                          VerifiedArtifact(url: link, sha256: original.sha256, byteSize: original.byteSize)]
        for candidate in candidates {
            do { _ = try await Exporter().save(candidate: candidate, stem: "part", directory: destination, protectedInputs: []); XCTFail("Accepted bad candidate") } catch {}
        }
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: destination.path), [])
    }

    func testInterruptedWriteAndPostPublishCorruptionCleanOwnedFiles() async throws {
        for checkpoint in [Exporter.Checkpoint.stageWritten, .beforePublication, .afterPublication] {
            let source = try temporaryDirectory(), destination = try temporaryDirectory()
            let candidate = try artifact(in: source)
            let exporter = Exporter { phase, url in
                if phase == checkpoint {
                    if phase == .stageWritten { throw LocalFileError.system("Injected disk full", ENOSPC) }
                    try Data("corrupted".utf8).write(to: url, options: [])
                }
            }
            do { _ = try await exporter.save(candidate: candidate, stem: "part", directory: destination, protectedInputs: []); XCTFail("Accepted corrupt/failed output") } catch {}
            XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: destination.path), [])
        }
    }

    func testConcurrentNameClaimDoesNotOverwrite() async throws {
        let source = try temporaryDirectory(), destination = try temporaryDirectory()
        let candidate = try artifact(in: source)
        async let first = Exporter().save(candidate: candidate, stem: "part", directory: destination, protectedInputs: [])
        async let second = Exporter().save(candidate: candidate, stem: "part", directory: destination, protectedInputs: [])
        let outputs = try await [first, second]
        XCTAssertEqual(Set(outputs.map(\.lastPathComponent)), Set(["part-fixed.stl", "part-fixed-2.stl"]))
        for url in outputs { try FileVerification.verify(VerifiedArtifact(url: url, sha256: candidate.sha256, byteSize: candidate.byteSize)) }
    }

    func testSubstitutedStageIsNeverPublishedOrDeleted() async throws {
        let source = try temporaryDirectory(), destination = try temporaryDirectory()
        let candidate = try artifact(in: source)
        let exporter = Exporter { phase, url in
            if phase == .beforePublication {
                try Data("foreign stage".utf8).write(to: url, options: .atomic)
            }
        }
        do { _ = try await exporter.save(candidate: candidate, stem: "part", directory: destination, protectedInputs: []); XCTFail("Published substituted stage") } catch {}
        XCTAssertFalse(FileManager.default.fileExists(atPath: destination.appendingPathComponent("part-fixed.stl").path))
        let stagingFolders = try FileManager.default.contentsOfDirectory(at: destination, includingPropertiesForKeys: nil)
        XCTAssertEqual(stagingFolders.count, 1)
        XCTAssertEqual(try Data(contentsOf: XCTUnwrap(stagingFolders.first).appendingPathComponent("candidate")), Data("foreign stage".utf8))
    }

    func testSubstitutedFinalIsPreservedAndSaveFails() async throws {
        let source = try temporaryDirectory(), destination = try temporaryDirectory()
        let candidate = try artifact(in: source)
        let exporter = Exporter { phase, url in
            if phase == .afterPublication {
                try Data("other user's replacement".utf8).write(to: url, options: .atomic)
            }
        }
        do { _ = try await exporter.save(candidate: candidate, stem: "part", directory: destination, protectedInputs: []); XCTFail("Accepted substituted final") } catch {}
        let output = destination.appendingPathComponent("part-fixed.stl")
        XCTAssertEqual(try Data(contentsOf: output), Data("other user's replacement".utf8))
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: destination.path), ["part-fixed.stl"])
    }

    func testOneFailedSaveDoesNotPreventLaterSave() async throws {
        let source = try temporaryDirectory(), destination = try temporaryDirectory()
        let candidate = try artifact(in: source)
        let exporter = Exporter()
        do { _ = try await exporter.save(candidate: candidate, stem: "bad/path", directory: destination, protectedInputs: []); XCTFail("Accepted invalid name") } catch {}
        let saved = try await exporter.save(candidate: candidate, stem: "good", directory: destination, protectedInputs: [])
        XCTAssertTrue(FileManager.default.fileExists(atPath: saved.path))
    }

    func testReadOnlyDestinationFailsWithoutOutput() async throws {
        guard getuid() != 0 else { throw XCTSkip("Root bypasses POSIX directory permissions") }
        let source = try temporaryDirectory(), destination = try temporaryDirectory()
        let candidate = try artifact(in: source)
        try FileManager.default.setAttributes([.posixPermissions: 0o500], ofItemAtPath: destination.path)
        defer { try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: destination.path) }
        do { _ = try await Exporter().save(candidate: candidate, stem: "part", directory: destination, protectedInputs: []); XCTFail("Wrote to read-only folder") } catch {}
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: destination.path), [])
    }

    func testAbandonedSnapshotRootIsReclaimedButLiveRootSurvives() async throws {
        let parent = try temporaryDirectory()
        let source = try artifact(in: parent)
        var abandoned: SnapshotStore? = try SnapshotStore(root: parent)
        let abandonedSnapshot = try await abandoned!.snapshot(source.url)
        let oldRoot = abandonedSnapshot.directory.deletingLastPathComponent()
        // Dropping the store releases its advisory lock, as process exit would.
        abandoned = nil
        let live = try SnapshotStore(root: parent)
        XCTAssertFalse(FileManager.default.fileExists(atPath: oldRoot.path))
        let liveSnapshot = try await live.snapshot(source.url)
        let another = try SnapshotStore(root: parent)
        XCTAssertTrue(FileManager.default.fileExists(atPath: liveSnapshot.input.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: source.url.path))
        try await another.cleanup()
        try await live.cleanup()
    }

    func testStaleCleanupPreservesUnmarkedRootsAndSymlinkTargets() async throws {
        let parent = try temporaryDirectory(), external = try temporaryDirectory()
        let externalFile = try artifact(in: external)
        let unmarked = parent.appendingPathComponent("zudo-stl-fix-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: unmarked, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        let unmarkedFile = try artifact(in: unmarked)
        let link = parent.appendingPathComponent("zudo-stl-fix-\(UUID().uuidString)")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: external)
        let markedLink = parent.appendingPathComponent("zudo-stl-fix-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: markedLink, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        try FileManager.default.createSymbolicLink(at: markedLink.appendingPathComponent(".owner.lock"), withDestinationURL: externalFile.url)
        let store = try SnapshotStore(root: parent)
        XCTAssertTrue(FileManager.default.fileExists(atPath: unmarkedFile.url.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: externalFile.url.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: link.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: markedLink.path))
        try await store.cleanup()
    }

    func testCopiedOwnershipMarkerDoesNotAuthorizeAnotherDirectory() async throws {
        let parent = try temporaryDirectory()
        let live = try SnapshotStore(root: parent)
        let root = await live.root
        let fake = parent.appendingPathComponent("zudo-stl-fix-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: fake, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        try FileManager.default.copyItem(at: root.appendingPathComponent(".owner.lock"),
                                         to: fake.appendingPathComponent(".owner.lock"))
        let protected = try artifact(in: fake)
        let next = try SnapshotStore(root: parent)
        XCTAssertTrue(FileManager.default.fileExists(atPath: protected.url.path))
        try await next.cleanup()
        try await live.cleanup()
    }
}
