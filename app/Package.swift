// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "ZudoSTLFix", platforms: [.macOS(.v14)],
    products: [.library(name: "ZudoSTLFixCore", targets: ["ZudoSTLFixCore"]), .executable(name: "ZudoSTLFix", targets: ["ZudoSTLFix"])],
    targets: [.target(name: "ZudoSTLFixCore"), .executableTarget(name: "ZudoSTLFix", dependencies: ["ZudoSTLFixCore"]), .testTarget(name: "ZudoSTLFixCoreTests", dependencies: ["ZudoSTLFixCore"])])
