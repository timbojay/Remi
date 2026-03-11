import Foundation

struct ConversationSummary: Identifiable, Codable {
    let id: String
    let title: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case updatedAt = "updated_at"
    }

    var displayTitle: String {
        title ?? "New conversation"
    }

    var displayDate: String {
        guard let updatedAt else { return "" }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: updatedAt) {
            let relative = RelativeDateTimeFormatter()
            relative.unitsStyle = .short
            return relative.localizedString(for: date, relativeTo: Date())
        }
        // Try without fractional seconds
        formatter.formatOptions = [.withInternetDateTime]
        if let date = formatter.date(from: updatedAt) {
            let relative = RelativeDateTimeFormatter()
            relative.unitsStyle = .short
            return relative.localizedString(for: date, relativeTo: Date())
        }
        return updatedAt
    }
}

struct ConversationDetail: Codable {
    let id: String
    let title: String?
    let messages: [ServerMessage]
}

struct ServerMessage: Codable {
    let id: String
    let role: String
    let content: String
    let timestamp: String
}
