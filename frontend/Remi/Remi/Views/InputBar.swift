import SwiftUI

struct InputBar: View {
    @Binding var text: String
    let isStreaming: Bool
    let onSend: () -> Void

    private var wordCount: Int {
        text.split(whereSeparator: { $0.isWhitespace || $0.isNewline }).count
    }

    private var canSend: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isStreaming
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 16) {
                Text(wordCount == 0 ? "" : "\(wordCount) word\(wordCount == 1 ? "" : "s")")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .frame(minWidth: 60, alignment: .leading)

                Spacer()

                Button {
                    text = ""
                } label: {
                    Image(systemName: "xmark.circle")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .disabled(text.isEmpty)

                Text("\u{2318} Return to send")
                    .font(.caption2)
                    .foregroundStyle(.quaternary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 4)

            HStack(alignment: .bottom, spacing: 10) {
                MultiLineTextView(
                    text: $text,
                    placeholder: "Tell me something about your life...",
                    font: .systemFont(ofSize: 14),
                    onCommandReturn: {
                        if canSend { onSend() }
                    }
                )
                .frame(minHeight: 60, maxHeight: 150)
                .background(Color.gray.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.gray.opacity(0.2), lineWidth: 1)
                )

                Button(action: onSend) {
                    Image(systemName: isStreaming ? "stop.circle.fill" : "arrow.up.circle.fill")
                        .font(.system(size: 28))
                        .foregroundStyle(canSend ? Color.accentColor : .gray)
                }
                .buttonStyle(.plain)
                .disabled(!canSend)
                .padding(.bottom, 8)
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 10)
        }
    }
}
