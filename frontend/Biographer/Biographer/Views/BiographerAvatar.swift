import Foundation
import SwiftUI

// MARK: - Avatar State

enum BiographerAvatarState {
    case idle      // Gentle breathing, eyes forward
    case thinking  // Eyes look up, thought bubbles
    case writing   // Eyes look down, typing bounce
}

// MARK: - Color Palette

private enum HedgehogColors {
    static let spikes = Color(red: 0.55, green: 0.35, blue: 0.20)
    static let bodyDark = Color(red: 0.65, green: 0.45, blue: 0.30)
    static let bodyLight = Color(red: 0.85, green: 0.75, blue: 0.60)
    static let belly = Color(red: 0.92, green: 0.85, blue: 0.75)
    static let nose = Color(red: 0.60, green: 0.35, blue: 0.30)
    static let glasses = Color(red: 0.30, green: 0.30, blue: 0.30)
}

// MARK: - Spikes Shape

struct SpikesShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let centerX = rect.midX
        let centerY = rect.maxY + 4
        let radius: CGFloat = rect.width * 0.52
        let spikeLength: CGFloat = rect.height * 0.55

        let spikeCount = 7
        let startAngle: CGFloat = 210
        let endAngle: CGFloat = 330
        let angleStep = (endAngle - startAngle) / CGFloat(spikeCount)

        let firstRad = CGFloat(Angle.degrees(Double(endAngle + angleStep / 2)).radians)
        path.move(to: CGPoint(
            x: centerX + radius * Foundation.cos(firstRad),
            y: centerY + radius * Foundation.sin(firstRad)
        ))

        for i in stride(from: spikeCount, through: 0, by: -1) {
            let tipAngleDeg = startAngle + CGFloat(i) * angleStep + angleStep / 2
            let tipRad = CGFloat(Angle.degrees(Double(tipAngleDeg)).radians)
            let baseAngleDeg = startAngle + CGFloat(i) * angleStep
            let baseRad = CGFloat(Angle.degrees(Double(baseAngleDeg)).radians)

            let tipRadius = radius + spikeLength
            path.addLine(to: CGPoint(
                x: centerX + tipRadius * Foundation.cos(tipRad),
                y: centerY + tipRadius * Foundation.sin(tipRad)
            ))

            path.addLine(to: CGPoint(
                x: centerX + radius * Foundation.cos(baseRad),
                y: centerY + radius * Foundation.sin(baseRad)
            ))
        }

        path.closeSubpath()
        return path
    }
}

// MARK: - Main Avatar View

struct BiographerAvatar: View {
    let state: BiographerAvatarState

    @State private var breathe = false
    @State private var writingBounce = false
    @State private var thoughtPulse = false
    @State private var isBlinking = false
    @State private var blinkTimer: Timer?

    private var pupilOffsetY: CGFloat {
        switch state {
        case .idle: return 0
        case .thinking: return -2.0
        case .writing: return 1.5
        }
    }

    var body: some View {
        ZStack {
            spikesView
            bodyView
            bellyView
            feetView
            eyesView
            glassesView
            noseView

            if state == .thinking {
                thoughtBubblesView
                    .transition(.opacity)
            }
        }
        .frame(width: 70, height: 70)
        .scaleEffect(breathe ? 1.0 : 0.97)
        .offset(y: (state == .writing && writingBounce) ? -2 : 0)
        .animation(.easeInOut(duration: 2.0).repeatForever(autoreverses: true), value: breathe)
        .animation(
            state == .writing
                ? .easeInOut(duration: 0.4).repeatForever(autoreverses: true)
                : .default,
            value: writingBounce
        )
        .animation(.spring(response: 0.5, dampingFraction: 0.7), value: state)
        .onAppear {
            breathe = true
            startBlinkTimer()
        }
        .onDisappear {
            blinkTimer?.invalidate()
            blinkTimer = nil
        }
        .onChange(of: state) { _, newState in
            writingBounce = (newState == .writing)
            thoughtPulse = (newState == .thinking)
        }
    }

    // MARK: - Sub-views

    private var spikesView: some View {
        SpikesShape()
            .fill(HedgehogColors.spikes)
            .frame(width: 50, height: 28)
            .offset(y: -16)
    }

    private var bodyView: some View {
        Ellipse()
            .fill(
                LinearGradient(
                    colors: [HedgehogColors.bodyLight, HedgehogColors.bodyDark],
                    startPoint: .bottom,
                    endPoint: .top
                )
            )
            .frame(width: 44, height: 38)
    }

    private var bellyView: some View {
        Ellipse()
            .fill(HedgehogColors.belly)
            .frame(width: 28, height: 20)
            .offset(y: 4)
    }

    private var feetView: some View {
        HStack(spacing: 14) {
            RoundedRectangle(cornerRadius: 3)
                .fill(HedgehogColors.bodyDark)
                .frame(width: 10, height: 5)
            RoundedRectangle(cornerRadius: 3)
                .fill(HedgehogColors.bodyDark)
                .frame(width: 10, height: 5)
        }
        .offset(y: 18)
    }

    private var eyesView: some View {
        HStack(spacing: 6) {
            singleEye
            singleEye
        }
        .offset(y: -4)
    }

    private var singleEye: some View {
        ZStack {
            Ellipse()
                .fill(.white)
                .frame(width: 11, height: isBlinking ? 2 : 10)

            if !isBlinking {
                Circle()
                    .fill(Color.primary)
                    .frame(width: 5, height: 5)
                    .offset(y: pupilOffsetY)

                Circle()
                    .fill(.white)
                    .frame(width: 2, height: 2)
                    .offset(x: 1.5, y: pupilOffsetY - 1.5)
            }
        }
    }

    private var glassesView: some View {
        ZStack {
            Circle()
                .stroke(HedgehogColors.glasses, lineWidth: 1.5)
                .frame(width: 14, height: 14)
                .offset(x: -8.5, y: -4)

            Circle()
                .stroke(HedgehogColors.glasses, lineWidth: 1.5)
                .frame(width: 14, height: 14)
                .offset(x: 8.5, y: -4)

            Rectangle()
                .fill(HedgehogColors.glasses)
                .frame(width: 4, height: 1.5)
                .offset(y: -4)

            Rectangle()
                .fill(HedgehogColors.glasses)
                .frame(width: 5, height: 1.5)
                .rotationEffect(.degrees(-10))
                .offset(x: -17, y: -3)

            Rectangle()
                .fill(HedgehogColors.glasses)
                .frame(width: 5, height: 1.5)
                .rotationEffect(.degrees(10))
                .offset(x: 17, y: -3)
        }
    }

    private var noseView: some View {
        Ellipse()
            .fill(HedgehogColors.nose)
            .frame(width: 5, height: 4)
            .offset(y: 5)
    }

    private var thoughtBubblesView: some View {
        Group {
            Circle()
                .fill(Color.secondary.opacity(0.3))
                .frame(width: 5, height: 5)
                .offset(x: 14, y: -28)

            Circle()
                .fill(Color.secondary.opacity(0.4))
                .frame(width: 7, height: 7)
                .offset(x: 19, y: -36)

            Circle()
                .fill(Color.secondary.opacity(0.5))
                .frame(width: 9, height: 9)
                .offset(x: 23, y: -45)
        }
        .opacity(thoughtPulse ? 1.0 : 0.5)
        .animation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true), value: thoughtPulse)
    }

    // MARK: - Blink Timer

    private func startBlinkTimer() {
        blinkTimer = Timer.scheduledTimer(withTimeInterval: 3.5, repeats: true) { _ in
            withAnimation(.easeInOut(duration: 0.08)) {
                isBlinking = true
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                withAnimation(.easeInOut(duration: 0.08)) {
                    isBlinking = false
                }
            }
        }
    }
}

// MARK: - Preview

#Preview("Avatar States") {
    HStack(spacing: 40) {
        VStack {
            BiographerAvatar(state: .idle)
            Text("Idle").font(.caption)
        }
        VStack {
            BiographerAvatar(state: .thinking)
            Text("Thinking").font(.caption)
        }
        VStack {
            BiographerAvatar(state: .writing)
            Text("Writing").font(.caption)
        }
    }
    .padding(50)
}
