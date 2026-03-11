import SwiftUI

#if os(macOS)
import AppKit

struct MultiLineTextView: NSViewRepresentable {
    @Binding var text: String
    var placeholder: String = ""
    var font: NSFont = .systemFont(ofSize: 14)
    var onCommandReturn: (() -> Void)? = nil

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        let textView = CommandReturnTextView()

        textView.delegate = context.coordinator
        textView.onCommandReturn = onCommandReturn
        textView.font = font
        textView.isRichText = false
        textView.allowsUndo = true
        textView.isEditable = true
        textView.isSelectable = true
        textView.drawsBackground = false
        textView.textContainerInset = NSSize(width: 8, height: 8)
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(width: 0, height: CGFloat.greatestFiniteMagnitude)

        scrollView.documentView = textView
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = false

        context.coordinator.textView = textView

        if !text.isEmpty {
            textView.string = text
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            textView.window?.makeFirstResponder(textView)
        }

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else { return }
        if textView.string != text {
            let selectedRange = textView.selectedRange()
            textView.string = text
            if selectedRange.location <= text.count {
                textView.setSelectedRange(selectedRange)
            }
        }
        textView.font = font
        context.coordinator.updatePlaceholder(textView)
    }

    class Coordinator: NSObject, NSTextViewDelegate {
        var parent: MultiLineTextView
        weak var textView: NSTextView?
        private var placeholderView: NSTextField?

        init(_ parent: MultiLineTextView) {
            self.parent = parent
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            parent.text = textView.string
            updatePlaceholder(textView)
        }

        func updatePlaceholder(_ textView: NSTextView) {
            if placeholderView == nil && !parent.placeholder.isEmpty {
                let label = NSTextField(labelWithString: parent.placeholder)
                label.textColor = .placeholderTextColor
                label.font = parent.font
                label.translatesAutoresizingMaskIntoConstraints = false
                label.isEditable = false
                label.isBezeled = false
                label.drawsBackground = false
                textView.addSubview(label)
                NSLayoutConstraint.activate([
                    label.topAnchor.constraint(equalTo: textView.topAnchor, constant: 8),
                    label.leadingAnchor.constraint(equalTo: textView.leadingAnchor, constant: 12),
                ])
                placeholderView = label
            }
            placeholderView?.isHidden = !textView.string.isEmpty
        }
    }
}

class CommandReturnTextView: NSTextView {
    var onCommandReturn: (() -> Void)?

    override func keyDown(with event: NSEvent) {
        if event.modifierFlags.contains(.command) && event.keyCode == 36 {
            onCommandReturn?()
            return
        }
        super.keyDown(with: event)
    }
}

#else
struct MultiLineTextView: View {
    @Binding var text: String
    var placeholder: String = ""
    var font: Any? = nil
    var onCommandReturn: (() -> Void)? = nil

    var body: some View {
        TextEditor(text: $text)
            .font(.body)
    }
}
#endif
