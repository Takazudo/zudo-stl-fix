import AppKit
import SwiftUI
import UniformTypeIdentifiers
import ZudoSTLFixCore

@MainActor final class AppDelegate: NSObject, NSApplicationDelegate {
    var queue: JobQueue?
    private var pendingURLs: [URL] = []
    var openFiles: (([URL]) -> Void)? {
        didSet {
            if let openFiles, !pendingURLs.isEmpty {
                let urls = pendingURLs; pendingURLs.removeAll(); openFiles(urls)
            }
        }
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let queue else { return .terminateNow }
        if queue.hasUnsavedWork {
            let alert = NSAlert(); alert.messageText = "Quit and discard unsaved work?"
            alert.informativeText = "Active checks will be canceled. Unsaved repaired copies will be removed. Original and saved files remain unchanged."
            alert.addButton(withTitle: "Keep Working"); alert.addButton(withTitle: "Quit")
            if alert.runModal() != .alertSecondButtonReturn { return .terminateCancel }
        }
        Task { await queue.shutdown(); sender.reply(toApplicationShouldTerminate: true) }
        return .terminateLater
    }
    func application(_ sender: NSApplication, open urls: [URL]) {
        if let openFiles { openFiles(urls) } else { pendingURLs.append(contentsOf: urls) }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

@MainActor private final class Startup: ObservableObject {
    @Published var queue: JobQueue?
    @Published var error: String?
    init() {
        Task {
            do {
                let store = try await Task.detached { try SnapshotStore() }.value
                queue = JobQueue(store: store)
            } catch { self.error = error.localizedDescription }
        }
    }
}

@main @MainActor struct ZudoSTLFixApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var startup = Startup()
    var body: some Scene {
        // A single Window: WindowGroup spawns one extra window per Finder-opened file.
        Window("zudo-stl-fix", id: "main") {
            if let queue = startup.queue {
                MainView(queue: queue)
                .frame(minWidth: 620, minHeight: 440)
                .onAppear {
                    delegate.queue = queue
                    delegate.openFiles = { urls in Task { await queue.add(urls) } }
                    NSApplication.shared.setActivationPolicy(.regular)
                    NSApplication.shared.activate(ignoringOtherApps: true)
                }
            } else if startup.error != nil {
                VStack(spacing: 16) {
                    Text("Unable to create a private workspace").font(.headline)
                    Text(startup.error ?? "Temporary storage is unavailable.").textSelection(.enabled)
                    Text("Check available disk space and temporary-folder permissions, then reopen the app.")
                }.padding(24).frame(width: 550)
            } else {
                ProgressView("Preparing private workspace…").padding(40)
            }
        }
        .defaultSize(width: 760, height: 560)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Open STL Files…") { chooseFiles { urls in Task { await startup.queue?.add(urls) } } }.keyboardShortcut("o").disabled(startup.queue == nil)
            }
        }
    }
}

@MainActor private func chooseFiles(_ action: @escaping ([URL]) -> Void) {
    let panel = NSOpenPanel(); panel.allowsMultipleSelection = true; panel.canChooseDirectories = false
    panel.allowedContentTypes = [UTType(filenameExtension: "stl") ?? .data]
    panel.prompt = "Check Files"
    panel.begin { response in if response == .OK { action(panel.urls) } }
}
@MainActor private func chooseFolder(_ action: @escaping (URL) -> Void) {
    let panel = NSOpenPanel(); panel.canChooseFiles = false; panel.canChooseDirectories = true
    panel.canCreateDirectories = true; panel.allowsMultipleSelection = false; panel.prompt = "Save Here"
    panel.begin { response in if response == .OK, let url = panel.url { action(url) } }
}

@MainActor private struct MainView: View {
    @ObservedObject var queue: JobQueue
    @State private var targeted = false
    @State private var detailID: UUID?
    @State private var advanced = false
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(spacing: 10) {
                Image(systemName: "tray.and.arrow.down").font(.largeTitle).accessibilityHidden(true)
                Text("Drop STL files here").font(.title2)
                Button("Choose Files…") { chooseFiles { urls in Task { await queue.add(urls) } } }
                if queue.importing { ProgressView("Making private copies…").controlSize(.small) }
            }
            .frame(maxWidth: .infinity).padding(22)
            .background(targeted ? Color.accentColor.opacity(0.12) : Color.secondary.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(targeted ? Color.accentColor : .secondary.opacity(0.3), style: StrokeStyle(lineWidth: 1, dash: [6])))
            .dropDestination(for: URL.self) { urls, _ in
                guard !urls.isEmpty else { return false }
                Task { await queue.add(urls) }; return true
            } isTargeted: { targeted = $0 }
            .accessibilityLabel("Drop local STL files here to check and conservatively repair")
            if !queue.inputMessages.isEmpty {
                HStack(alignment: .top) {
                    ScrollView { Text(queue.inputMessages.suffix(20).joined(separator: "\n")).font(.caption).foregroundStyle(.orange).frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled) }.frame(maxHeight: 65)
                    Button("Dismiss") { queue.clearMessages() }.controlSize(.small)
                }
            }
            List(queue.jobs) { job in
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(job.name).lineLimit(1).truncationMode(.middle).help(job.snapshot.original.path)
                            HStack(spacing: 6) {
                                if job.status.active || job.status == .saving { ProgressView().controlSize(.small) }
                                Text(job.status.rawValue).font(.callout).foregroundStyle(statusColor(job.status))
                            }
                        }
                        Spacer()
                        if job.status.active { Button("Cancel") { queue.cancel(job.id) } }
                        if job.status.canSave { Button("Save…") { chooseFolder { url in Task { await queue.save([job.id], to: url) } } } }
                        if let saved = job.savedURL { Button("Reveal") { NSWorkspace.shared.activateFileViewerSelecting([saved]) }.help("Reveal in Finder") }
                        Button("Details") { detailID = job.id }
                        if !job.status.active && job.status != .saving {
                            Button { queue.discard(job.id) } label: { Image(systemName: "xmark") }.help("Remove from queue and discard unsaved candidate").accessibilityLabel("Remove \(job.name)")
                        }
                    }
                    ForEach(Array(job.warnings.enumerated()), id: \.offset) { _, text in
                        Label(text, systemImage: "exclamationmark.triangle").font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
                    }
                    if !job.message.isEmpty { Text(job.message).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
                }.padding(.vertical, 5)
            }.listStyle(.inset)
            DisclosureGroup("Advanced", isExpanded: $advanced) {
                VStack(alignment: .leading, spacing: 6) {
                    Toggle("Merge tiny existing edges", isOn: $queue.mergeTinyEdges)
                    HStack {
                        Text("Tolerance (STL coordinate units)")
                        TextField("0.00001", text: $queue.toleranceText).frame(width: 100).disabled(!queue.mergeTinyEdges)
                    }
                    Text("Off by default. Applies to new files only; this may move vertices and is recorded in Details. Units and printing suitability are not inferred.").font(.caption).foregroundStyle(.secondary)
                }.padding(.top, 6)
            }
            HStack {
                Button("Clear Finished") { queue.clearFinished() }
                Spacer()
                Text("Local processing · Originals stay unchanged").font(.caption).foregroundStyle(.secondary)
                Button("Save Fixed Files…") { chooseFolder { url in Task { await queue.save(queue.readyIDs, to: url) } } }.disabled(queue.readyIDs.isEmpty)
            }
        }.padding(16)
        .sheet(isPresented: Binding(get: { detailID != nil }, set: { if !$0 { detailID = nil } })) {
            if let id = detailID, let job = queue.jobs.first(where: { $0.id == id }) {
                VStack(alignment: .leading, spacing: 12) {
                    Text(job.name).font(.headline)
                    ScrollView { Text(job.details).font(.system(.body, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                    HStack {
                        if job.result?.report != nil {
                            Button("Export JSON Report…") { chooseFolder { url in Task { await queue.exportReport(id, to: url) } } }
                        }
                        Spacer(); Button("Done") { detailID = nil }.keyboardShortcut(.defaultAction)
                    }
                }.padding(20).frame(minWidth: 580, minHeight: 420)
            }
        }
    }
    private func statusColor(_ status: JobStatus) -> Color {
        switch status {
        case .error, .refused: return .red
        case .incomplete, .review: return .orange
        case .ready, .saved, .unchanged: return .primary
        default: return .secondary
        }
    }
}
