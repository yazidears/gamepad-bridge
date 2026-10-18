import AppKit
import AVFoundation
import ScreenCaptureKit
import Darwin

// Audio output only: this stream never attaches a screen or microphone output.
final class AudioCapture: NSObject, SCStreamOutput, SCStreamDelegate {
    let socketFD: Int32
    let directory: URL
    var stream: SCStream?
    private var pending = Data()
    private var blocks = 0, nonzeroBlocks = 0
    private var lastReport = Date.distantPast
    init(directory: URL) throws {
        self.directory = directory
        socketFD = socket(AF_UNIX, SOCK_DGRAM, 0)
        guard socketFD >= 0 else { throw POSIXError(.EIO) }
        super.init()
        let path = directory.appendingPathComponent("audio-input.sock").path
        guard path.utf8.count < 104 else { throw POSIXError(.ENAMETOOLONG) }
        var address = sockaddr_un(); address.sun_family = sa_family_t(AF_UNIX)
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        withUnsafeMutableBytes(of: &address.sun_path) { $0.copyBytes(from: Array(path.utf8)+[0]) }
        let result = withUnsafePointer(to: &address) { p in
            p.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.connect(socketFD, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) }
        }
        guard result == 0 else { throw POSIXError(.ECONNREFUSED) }
        _ = fcntl(socketFD, F_SETFL, O_NONBLOCK)
    }
    deinit { close(socketFD) }
    func report(_ status: [String: Any]) {
        if let data = try? JSONSerialization.data(withJSONObject: status) {
            let path = directory.appendingPathComponent("audio-capture-status.json")
            try? data.write(to: path, options: .atomic); chmod(path.path, 0o600)
        }
    }
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        report(["active":false,"errorCode":(error as NSError).code])
        exit(3)
    }
    func stream(_ stream: SCStream, didOutputSampleBuffer sample: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, CMSampleBufferIsValid(sample),
            let desc = CMSampleBufferGetFormatDescription(sample),
            let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(desc),
            let format = AVAudioFormat(streamDescription: asbd), format.sampleRate == 48000 else { return }
        let count = CMSampleBufferGetNumSamples(sample)
        guard count > 0, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(count)) else { return }
        buffer.frameLength = AVAudioFrameCount(count)
        guard CMSampleBufferCopyPCMDataIntoAudioBufferList(sample, at: 0, frameCount: Int32(count), into: buffer.mutableAudioBufferList) == noErr else { return }
        let channels = Int(format.channelCount)
        var pcm = [Int16](repeating: 0, count: count*2)
        if let planes = buffer.floatChannelData {
            let interleaved = format.isInterleaved
            for i in 0..<count { for ch in 0..<2 {
                let sourceChannel = min(ch, channels-1)
                let value = interleaved ? planes[0][i*channels+sourceChannel] : planes[sourceChannel][i]
                pcm[i*2+ch] = value.isFinite ? Int16(max(-32767, min(32767, value*32767))) : 0
            }}
        } else if let planes = buffer.int16ChannelData {
            for i in 0..<count { for ch in 0..<2 {
                let sourceChannel = min(ch, channels-1)
                pcm[i*2+ch] = format.isInterleaved ? planes[0][i*channels+sourceChannel] : planes[sourceChannel][i]
            }}
        } else { return }
        pcm.withUnsafeBytes { pending.append(contentsOf: $0) }
        while pending.count >= 960 {
            let data = pending.prefix(960)
            let sent = data.withUnsafeBytes { Darwin.send(socketFD, $0.baseAddress, $0.count, 0) }
            if sent == 960 { blocks += 1; if data.contains(where: { $0 != 0 }) { nonzeroBlocks += 1 } }
            pending.removeFirst(960)
        }
        if Date().timeIntervalSince(lastReport) > 2 {
            lastReport = Date()
            report(["active":true,"blocks":blocks,"nonzeroBlocks":nonzeroBlocks,"sampleRate":48000,"channels":2])
        }
    }
}

@main struct Main {
    @MainActor static func main() async {
        NSApplication.shared.setActivationPolicy(.prohibited)
        guard CommandLine.arguments.count == 2 else { return }
        let directory = URL(fileURLWithPath: CommandLine.arguments[1])
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
            guard let display = content.displays.first(where: { $0.displayID == CGMainDisplayID() }) ?? content.displays.first else { return }
            // Mirror the Mac's audible mix, including helper-process playback.
            // Only .audio is attached below; no desktop images are requested.
            let filter = SCContentFilter(display: display, excludingWindows: [])
            let configuration = SCStreamConfiguration()
            configuration.width = 2; configuration.height = 2
            configuration.capturesAudio = true; configuration.sampleRate = 48000; configuration.channelCount = 2
            configuration.excludesCurrentProcessAudio = true
            let capture = try AudioCapture(directory: directory)
            let stream = SCStream(filter: filter, configuration: configuration, delegate: capture)
            capture.stream = stream
            try stream.addStreamOutput(capture, type: .audio, sampleHandlerQueue: DispatchQueue(label: "gamepad.audio"))
            try await stream.startCapture()
            capture.report(["active":true,"blocks":0,"nonzeroBlocks":0])
            while true { try await Task.sleep(for: .seconds(60)); _ = capture.stream }
        } catch {
            let data = try? JSONSerialization.data(withJSONObject: ["active":false,"errorCode":(error as NSError).code])
            if let data {
                let path = directory.appendingPathComponent("audio-capture-status.json")
                try? data.write(to: path, options: .atomic); chmod(path.path, 0o600)
            }
        }
    }
}
