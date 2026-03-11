import Foundation

enum MessageRole: String, Codable {
    case user
    case assistant
    case system
}

struct Message: Identifiable, Equatable {
    let id: String
    let role: MessageRole
    var content: String
    let timestamp: Date

    init(id: String = UUID().uuidString, role: MessageRole, content: String, timestamp: Date = Date()) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
    }
}

struct ChatRequest: Codable {
    let message: String
    let conversationId: String?

    enum CodingKeys: String, CodingKey {
        case message
        case conversationId = "conversation_id"
    }
}

struct StreamChunk: Codable {
    let content: String
    let done: Bool
    let conversationId: String?

    enum CodingKeys: String, CodingKey {
        case content
        case done
        case conversationId = "conversation_id"
    }
}
