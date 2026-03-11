import Foundation

class APIClient {
    private let baseURL: String
    private let streamSession: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 180
        config.timeoutIntervalForResource = 300
        return URLSession(configuration: config)
    }()

    init(baseURL: String = "http://127.0.0.1:8001") {
        self.baseURL = baseURL
    }

    // MARK: - Health

    func healthCheck() async -> Bool {
        guard let url = URL(string: "\(baseURL)/api/health") else { return false }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
               let status = json["status"] as? String {
                return status == "ok"
            }
        } catch {}
        return false
    }

    func getHealth() async -> HealthResponse? {
        await fetchJSON("\(baseURL)/api/health")
    }

    // MARK: - Conversations

    func listConversations() async -> [ConversationSummary] {
        guard let url = URL(string: "\(baseURL)/api/conversations") else { return [] }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            return try JSONDecoder().decode([ConversationSummary].self, from: data)
        } catch {
            return []
        }
    }

    func getConversation(id: String) async -> ConversationDetail? {
        guard let url = URL(string: "\(baseURL)/api/conversations/\(id)") else { return nil }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            return try JSONDecoder().decode(ConversationDetail.self, from: data)
        } catch {
            return nil
        }
    }

    // MARK: - Chat Streaming

    func streamChat(message: String, conversationId: String?) -> AsyncThrowingStream<StreamChunk, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard let url = URL(string: "\(baseURL)/api/chat/stream") else {
                        continuation.finish(throwing: URLError(.badURL))
                        return
                    }

                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

                    let body = ChatRequest(message: message, conversationId: conversationId)
                    request.httpBody = try JSONEncoder().encode(body)

                    let (bytes, response) = try await streamSession.bytes(for: request)

                    guard let httpResponse = response as? HTTPURLResponse,
                          httpResponse.statusCode == 200 else {
                        continuation.finish(throwing: URLError(.badServerResponse))
                        return
                    }

                    let decoder = JSONDecoder()
                    for try await line in bytes.lines {
                        guard !line.isEmpty else { continue }
                        guard let data = line.data(using: .utf8) else { continue }
                        let chunk = try decoder.decode(StreamChunk.self, from: data)
                        continuation.yield(chunk)
                        if chunk.done { break }
                    }

                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    // MARK: - Knowledge Graph

    func getEntities(type: String? = nil) async -> [Entity] {
        var urlString = "\(baseURL)/api/entities"
        if let type { urlString += "?entity_type=\(type)" }
        let response: EntityListResponse? = await fetchJSON(urlString)
        return response?.entities ?? []
    }

    func getFacts(category: String? = nil) async -> [Fact] {
        var urlString = "\(baseURL)/api/facts"
        if let category { urlString += "?category=\(category)" }
        let response: FactListResponse? = await fetchJSON(urlString)
        return response?.facts ?? []
    }

    func getRelationships() async -> [Relationship] {
        let response: RelationshipListResponse? = await fetchJSON("\(baseURL)/api/relationships")
        return response?.relationships ?? []
    }

    func getFamilyTree() async -> FamilyTreeResponse? {
        await fetchJSON("\(baseURL)/api/family-tree")
    }

    func getTimeline() async -> [TimelineEvent] {
        let response: TimelineResponse? = await fetchJSON("\(baseURL)/api/timeline")
        return response?.events ?? []
    }

    func getCoverage() async -> CoverageResponse? {
        await fetchJSON("\(baseURL)/api/coverage")
    }

    // MARK: - Biography

    func getBiography() async -> BiographyResponse? {
        await fetchJSON("\(baseURL)/api/biography")
    }

    // MARK: - Greeting

    func getGreeting() async -> String? {
        struct GreetingResponse: Decodable {
            let greeting: String
        }
        let response: GreetingResponse? = await fetchJSON("\(baseURL)/api/greet")
        return response?.greeting
    }

    // MARK: - Helpers

    private func fetchJSON<T: Decodable>(_ urlString: String) async -> T? {
        guard let url = URL(string: urlString) else { return nil }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            print("API error (\(urlString)): \(error)")
            return nil
        }
    }
}
