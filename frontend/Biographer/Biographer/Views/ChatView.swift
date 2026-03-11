import SwiftUI

struct ChatView: View {
    @Bindable var viewModel: ChatViewModel

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                BiographerAvatar(state: viewModel.avatarState)
                    .scaleEffect(0.6)
                    .frame(width: 42, height: 42)

                Text("Biographer")
                    .font(.title2)
                    .fontWeight(.semibold)
                Spacer()

                Circle()
                    .fill(viewModel.isBackendOnline ? Color.green : Color.red)
                    .frame(width: 8, height: 8)

                Text(viewModel.isBackendOnline ? "Online" : "Offline")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal)
            .padding(.vertical, 8)

            Divider()

            // Messages or empty state
            ZStack {
                if viewModel.messages.isEmpty {
                    VStack(spacing: 16) {
                        BiographerAvatar(state: viewModel.isLoadingGreeting ? .thinking : .idle)

                        if viewModel.isLoadingGreeting {
                            ProgressView()
                                .controlSize(.small)
                        } else if let greeting = viewModel.greeting {
                            Text(greeting)
                                .font(.body)
                                .foregroundStyle(.primary)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal, 60)
                                .transition(.opacity)
                        } else {
                            Text("Start a new conversation or select one from the sidebar")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal, 40)
                        }
                    }
                }

                if !viewModel.messages.isEmpty {
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(spacing: 12) {
                                ForEach(viewModel.messages) { message in
                                    MessageBubble(message: message)
                                        .id(message.id)
                                }
                            }
                            .padding()
                        }
                        .onChange(of: viewModel.messages.last?.content) {
                            if let lastId = viewModel.messages.last?.id {
                                withAnimation(.easeOut(duration: 0.2)) {
                                    proxy.scrollTo(lastId, anchor: .bottom)
                                }
                            }
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            Divider()

            InputBar(
                text: $viewModel.inputText,
                isStreaming: viewModel.isStreaming,
                onSend: { viewModel.sendMessage() }
            )
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
