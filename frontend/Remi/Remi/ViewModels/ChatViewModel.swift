import Foundation
import SwiftUI

@Observable
class ChatViewModel {
    var messages: [Message] = []
    var inputText: String = ""
    var isStreaming: Bool = false
    var isWaitingForResponse: Bool = false
    var isBackendOnline: Bool = false
    var greeting: String?
    var isLoadingGreeting: Bool = false
    var conversationId: String?
    var conversations: [ConversationSummary] = []
    var selectedConversationId: String?

    var avatarState: RemiAvatarState {
        if isWaitingForResponse { return .thinking }
        if isStreaming { return .writing }
        return .idle
    }

    private let apiClient = APIClient()

    func checkBackendHealth() async {
        isBackendOnline = await apiClient.healthCheck()
        if isBackendOnline {
            await fetchGreeting()
        }
    }

    func fetchGreeting() async {
        guard messages.isEmpty, conversationId == nil else { return }
        isLoadingGreeting = true
        greeting = await apiClient.getGreeting()
        isLoadingGreeting = false
    }

    func loadConversations() async {
        conversations = await apiClient.listConversations()
    }

    func loadConversation(id: String) async {
        guard let detail = await apiClient.getConversation(id: id) else { return }
        conversationId = detail.id
        messages = detail.messages.compactMap { serverMsg in
            guard let role = MessageRole(rawValue: serverMsg.role) else { return nil }
            return Message(
                id: serverMsg.id,
                role: role,
                content: serverMsg.content,
                timestamp: ISO8601DateFormatter().date(from: serverMsg.timestamp) ?? Date()
            )
        }
    }

    func startNewConversation() {
        conversationId = nil
        messages = []
        selectedConversationId = nil
        Task {
            await fetchGreeting()
        }
    }

    func selectConversation(id: String?) async {
        selectedConversationId = id
        if let id {
            guard conversationId != id else { return }
            await loadConversation(id: id)
        } else {
            startNewConversation()
        }
    }

    func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isStreaming else { return }

        let userMessage = Message(role: .user, content: text)
        messages.append(userMessage)
        inputText = ""

        let assistantMessage = Message(role: .assistant, content: "")
        let assistantId = assistantMessage.id
        messages.append(assistantMessage)

        isStreaming = true
        isWaitingForResponse = true

        Task {
            do {
                for try await chunk in apiClient.streamChat(message: text, conversationId: conversationId) {
                    await MainActor.run {
                        isWaitingForResponse = false
                        if let idx = messages.firstIndex(where: { $0.id == assistantId }) {
                            messages[idx].content += chunk.content
                        }
                        if conversationId == nil, let id = chunk.conversationId {
                            conversationId = id
                            selectedConversationId = id
                        }
                    }
                }
            } catch {
                await MainActor.run {
                    if let idx = messages.firstIndex(where: { $0.id == assistantId }) {
                        messages[idx].content = "Sorry, I couldn't connect to the backend. Make sure the Remi server is running."
                    }
                }
            }

            await MainActor.run {
                if let idx = messages.firstIndex(where: { $0.id == assistantId }),
                   messages[idx].content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    messages[idx].content = "I hear you — please go on, I'm listening."
                }
                isStreaming = false
                isWaitingForResponse = false
            }

            // Refresh conversation list after sending
            await loadConversations()
        }
    }
}
