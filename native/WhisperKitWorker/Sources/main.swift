import Foundation
import WhisperKit

private let protocolVersion = 1

private func emit(_ body: [String: Any]) {
    guard JSONSerialization.isValidJSONObject(body),
          let data = try? JSONSerialization.data(withJSONObject: body),
          let line = String(data: data, encoding: .utf8) else { return }
    print(line)
    fflush(stdout)
}

private func emitError(_ id: String?, _ message: String) {
    emit(["version": protocolVersion, "id": id ?? "", "type": "error", "message": message])
}

private func pcmToFloats(_ encoded: String) throws -> [Float] {
    guard let data = Data(base64Encoded: encoded), data.count.isMultiple(of: 2) else {
        throw NSError(domain: "what", code: 1, userInfo: [NSLocalizedDescriptionKey: "invalid s16le audio"])
    }
    return data.withUnsafeBytes { raw in
        let samples = raw.bindMemory(to: Int16.self)
        return samples.map { Float(Int16(littleEndian: $0)) / 32768.0 }
    }
}

// Whisper emits non-speech markers like [BLANK_AUDIO], [MUSIC], [APPLAUSE] when
// decoding silence or noise. That is common here because we pad short chunks with
// trailing silence and the pipeline force-decodes some non-speech chunks, so these
// leak into captions. skipSpecialTokens doesn't catch them (they render as text).
// Strip bracketed all-caps markers so blank segments collapse to empty text (which
// the pipeline then drops).
private func stripNonSpeechMarkers(_ s: String) -> String {
    let cleaned = s.replacingOccurrences(
        of: "\\[[A-Z0-9_ ]+\\]", with: "", options: .regularExpression)
    return cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
}

private func resultJSON(_ results: [TranscriptionResult]) -> [String: Any] {
    var bestAvgLogprob: Float? = nil
    let segments: [[String: Any]] = results.flatMap(\.segments).compactMap { segment in
        let segText = stripNonSpeechMarkers(segment.text)
        if segText.isEmpty { return nil }
        // Match faster_whisper: best_avg_logprob is the max over kept segments, so the
        // pipeline's min_avg_logprob gate behaves the same on the Metal backend.
        if bestAvgLogprob == nil || segment.avgLogprob > bestAvgLogprob! {
            bestAvgLogprob = segment.avgLogprob
        }
        var body: [String: Any] = [
            "start": Double(segment.start),
            "end": Double(segment.end),
            "text": segText,
            "avg_logprob": Double(segment.avgLogprob),
        ]
        if let words = segment.words {
            body["words"] = words.map { ["word": $0.word, "start": Double($0.start), "end": Double($0.end)] }
        }
        return body
    }
    let text = stripNonSpeechMarkers(results.map(\.text).joined())
    let language = results.first?.language ?? ""
    return [
        "text": text,
        "segments": segments,
        "language": language,
        "language_probability": 0.0,
        "best_avg_logprob": bestAvgLogprob.map { Double($0) } ?? NSNull(),
    ]
}

@main
struct WhatWhisperKitWorker {
    static func main() async {
        let arguments = CommandLine.arguments
        let model = arguments.drop(while: { $0 != "--model" }).dropFirst().first ?? "large-v3"
        // WhisperKit defaults its model cache to ~/Documents/huggingface, which is a
        // TCC-protected folder on macOS -- the worker can't manage the cache there,
        // so a corrupted/partial download becomes unrecoverable ("couldn't be removed
        // because you don't have permission"). Download to ~/Library/Caches instead
        // (not TCC-protected). Override with WHAT_WHISPERKIT_DOWNLOAD_BASE.
        let env = ProcessInfo.processInfo.environment
        let downloadBase: URL = {
            if let p = env["WHAT_WHISPERKIT_DOWNLOAD_BASE"], !p.isEmpty {
                return URL(fileURLWithPath: p, isDirectory: true)
            }
            let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
                ?? URL(fileURLWithPath: NSTemporaryDirectory())
            return caches.appendingPathComponent("what-whisperkit", isDirectory: true)
        }()
        // Once the model is cached, load it strictly from disk. WhisperKit's normal
        // path still calls HubApi.snapshot() to resolve the repo against HuggingFace
        // even when every file is already present, so a flaky/offline network makes
        // init throw downloadError("...offline") intermittently -- the worker dies and
        // the service produces no captions. Passing an existing modelFolder (+ the
        // cached tokenizer under downloadBase) makes WhisperKit skip all network I/O.
        let variant = model.hasPrefix("openai_whisper-") ? model : "openai_whisper-\(model)"
        let modelFolderURL = downloadBase
            .appendingPathComponent("models", isDirectory: true)
            .appendingPathComponent("argmaxinc", isDirectory: true)
            .appendingPathComponent("whisperkit-coreml", isDirectory: true)
            .appendingPathComponent(variant, isDirectory: true)
        // A model folder that merely exists is not a usable model: an interrupted
        // download/conversion leaves .mlmodelc directories without their weights, and
        // loading those fails with the opaque "Error in reading the MIL network". Name
        // the missing files and stop instead; a runtime re-download of anything but the
        // smallest models would not finish within the service's startup timeout anyway.
        let fm = FileManager.default
        let requiredFiles = ["config.json"] + ["MelSpectrogram", "AudioEncoder", "TextDecoder"]
            .flatMap { component in
                ["coremldata.bin", "model.mil", "weights/weight.bin"]
                    .map { "\(component).mlmodelc/\($0)" }
            }
        let missingFiles = requiredFiles.filter {
            !fm.fileExists(atPath: modelFolderURL.appendingPathComponent($0).path)
        }
        let cached = missingFiles.isEmpty
        if !cached && fm.fileExists(atPath: modelFolderURL.path) {
            fputs("[worker] cached model \(variant) is incomplete at \(modelFolderURL.path)\n", stderr)
            fputs("[worker] missing: \(missingFiles.joined(separator: ", "))\n", stderr)
            fputs("[worker] remove that folder to re-download it, or choose another model\n", stderr)
            exit(2)
        }
        let config: WhisperKitConfig
        if cached {
            fputs("[worker] loading cached model offline from \(modelFolderURL.path)\n", stderr)
            config = WhisperKitConfig(
                model: model,
                downloadBase: downloadBase,
                modelFolder: modelFolderURL.path,
                tokenizerFolder: downloadBase,
                download: false)
        } else {
            fputs("[worker] model not cached; downloading \(variant)\n", stderr)
            config = WhisperKitConfig(model: model, downloadBase: downloadBase)
        }
        do {
            let kit = try await WhisperKit(config)
            while let line = readLine() {
                guard let data = line.data(using: .utf8),
                      let request = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let id = request["id"] as? String,
                      let type = request["type"] as? String,
                      (request["version"] as? Int) == protocolVersion else {
                    emitError(nil, "invalid protocol-v1 request")
                    continue
                }
                switch type {
                case "ready":
                    emit(["version": protocolVersion, "id": id, "type": "ready", "engine": "whisperkit"])
                case "shutdown":
                    emit(["version": protocolVersion, "id": id, "type": "shutdown"])
                    return
                case "transcribe":
                    do {
                        guard let encoded = request["pcm_s16le_b64"] as? String else {
                            throw NSError(domain: "what", code: 2, userInfo: [NSLocalizedDescriptionKey: "missing audio"])
                        }
                        let language = request["language"] as? String
                        // Live-tunable decode gates from asr_cfg (rantbank -> /control/asr).
                        // WhisperKit's DecodingOptions leaves these at its defaults when the
                        // field is absent; a present value overrides per-decode.
                        var options = DecodingOptions(language: language, skipSpecialTokens: true, wordTimestamps: true)
                        if let v = request["no_speech_threshold"] as? Double { options.noSpeechThreshold = Float(v) }
                        if let v = request["logprob_threshold"] as? Double { options.logProbThreshold = Float(v) }
                        if let v = request["compression_ratio_threshold"] as? Double { options.compressionRatioThreshold = Float(v) }
                        // WhisperKit returns an empty transcript (and short-circuits in
                        // ~0ms) for audio shorter than ~1.5s. The live pipeline emits
                        // sub-second chunks, so pad short buffers with trailing silence to
                        // a safe minimum -- the speech at the front still decodes and the
                        // silence yields nothing. Without this, live captions never appear.
                        let sampleRate = (request["sample_rate"] as? Int) ?? 16000
                        var samples = try pcmToFloats(encoded)
                        let minSamples = Int(Double(sampleRate) * 2.0)
                        if samples.count < minSamples {
                            samples.append(contentsOf: repeatElement(Float(0), count: minSamples - samples.count))
                        }
                        let results = try await kit.transcribe(audioArray: samples, decodeOptions: options)
                        emit(["version": protocolVersion, "id": id, "type": "final", "result": resultJSON(results)])
                    } catch {
                            emitError(id, error.localizedDescription)
                    }
                default:
                    emitError(id, "unsupported request type: \(type)")
                }
            }
        } catch {
            fputs("WhisperKit initialization failed: \(error.localizedDescription)\n", stderr)
        }
    }
}
