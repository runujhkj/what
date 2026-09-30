// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WhatWhisperKitWorker",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "what-whisperkit-worker", targets: ["WhatWhisperKitWorker"]),
    ],
    dependencies: [
        .package(url: "https://github.com/argmaxinc/argmax-oss-swift", from: "1.0.0"),
    ],
    targets: [
        .executableTarget(
            name: "WhatWhisperKitWorker",
            dependencies: [.product(name: "WhisperKit", package: "argmax-oss-swift")],
            path: "Sources"
        ),
    ]
)
