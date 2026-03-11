import Foundation

// MARK: - Entity

struct Entity: Identifiable, Codable, Equatable {
    let id: String
    let name: String
    let entityType: String
    let relationship: String?
    let familyRole: String?
    let description: String?
    let confidence: Double?
    let mentionCount: Int?
    let isVerified: Int?

    enum CodingKeys: String, CodingKey {
        case id, name, description, confidence
        case entityType = "entity_type"
        case relationship
        case familyRole = "family_role"
        case mentionCount = "mention_count"
        case isVerified = "is_verified"
    }

    var displayType: String {
        entityType.replacingOccurrences(of: "_", with: " ").capitalized
    }

    var icon: String {
        switch entityType {
        case "person": return "person.fill"
        case "place": return "mappin.and.ellipse"
        case "school": return "graduationcap.fill"
        case "organization": return "building.2.fill"
        case "book": return "book.fill"
        case "film": return "film"
        case "music": return "music.note"
        default: return "tag"
        }
    }
}

struct EntityListResponse: Codable {
    let entities: [Entity]
    let count: Int
}

// MARK: - Fact

struct Fact: Identifiable, Codable, Equatable {
    let id: String
    let value: String
    let category: String
    let predicate: String?
    let confidence: Double?
    let significance: Int?
    let isVerified: Int?
    let dateYear: Int?
    let dateMonth: Int?
    let era: String?

    enum CodingKeys: String, CodingKey {
        case id, value, category, predicate, confidence, significance, era
        case isVerified = "is_verified"
        case dateYear = "date_year"
        case dateMonth = "date_month"
    }

    var displayCategory: String {
        category.replacingOccurrences(of: "_", with: " ").capitalized
    }

    var categoryIcon: String {
        switch category {
        case "identity": return "person.text.rectangle"
        case "family": return "figure.2.and.child.holdinghands"
        case "education": return "graduationcap"
        case "career": return "briefcase"
        case "residence": return "house"
        case "milestone": return "star.fill"
        case "childhood": return "teddybear"
        case "relationships": return "heart"
        case "hobbies": return "paintpalette"
        case "health": return "heart.text.square"
        case "travel": return "airplane"
        case "beliefs": return "sparkles"
        case "daily_life": return "cup.and.saucer"
        case "challenges": return "mountain.2"
        case "dreams": return "cloud"
        default: return "doc.text"
        }
    }
}

struct FactListResponse: Codable {
    let facts: [Fact]
    let count: Int
}

// MARK: - Relationship

struct Relationship: Identifiable, Codable {
    let id: String
    let relationshipType: String
    let isBidirectional: Int
    let confidence: Double
    let fromName: String
    let fromId: String
    let toName: String
    let toId: String

    enum CodingKeys: String, CodingKey {
        case id, confidence
        case relationshipType = "relationship_type"
        case isBidirectional = "is_bidirectional"
        case fromName = "from_name"
        case fromId = "from_id"
        case toName = "to_name"
        case toId = "to_id"
    }

    var displayType: String {
        relationshipType.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

struct RelationshipListResponse: Codable {
    let relationships: [Relationship]
    let count: Int
}

// MARK: - Family Tree

struct FamilyTreePerson: Identifiable, Codable {
    let id: String
    let name: String
    let entityType: String
    let relationship: String?
    let familyRole: String?
    let description: String?

    enum CodingKeys: String, CodingKey {
        case id, name, description, relationship
        case entityType = "entity_type"
        case familyRole = "family_role"
    }
}

struct FamilyTreeResponse: Codable {
    let people: [FamilyTreePerson]
    let relationships: [FamilyRelLink]
    let byRole: [String: [FamilyRolePerson]]

    enum CodingKeys: String, CodingKey {
        case people, relationships
        case byRole = "by_role"
    }
}

struct FamilyRelLink: Codable {
    let fromEntityId: String
    let toEntityId: String
    let relationshipType: String
    let isBidirectional: Int
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case confidence
        case fromEntityId = "from_entity_id"
        case toEntityId = "to_entity_id"
        case relationshipType = "relationship_type"
        case isBidirectional = "is_bidirectional"
    }
}

struct FamilyRolePerson: Identifiable, Codable {
    let id: String
    let name: String
    let role: String
    let description: String?
}

// MARK: - Timeline

struct TimelineEvent: Identifiable, Codable {
    let id: String
    let value: String
    let category: String
    let dateYear: Int?
    let dateMonth: Int?
    let era: String?
    let significance: Int?
    let confidence: Double?
    let isVerified: Int?
    let subjectName: String?

    enum CodingKeys: String, CodingKey {
        case id, value, category, era, significance, confidence
        case dateYear = "date_year"
        case dateMonth = "date_month"
        case isVerified = "is_verified"
        case subjectName = "subject_name"
    }

    var displayDate: String {
        if let year = dateYear {
            if let month = dateMonth {
                let formatter = DateFormatter()
                formatter.dateFormat = "MMMM"
                if let date = Calendar.current.date(from: DateComponents(month: month)) {
                    return "\(formatter.string(from: date)) \(year)"
                }
            }
            return "\(year)"
        }
        return era ?? "Unknown"
    }
}

struct TimelineResponse: Codable {
    let events: [TimelineEvent]
    let count: Int
}

// MARK: - Coverage

struct CoverageItem: Identifiable, Codable {
    var id: String { category }
    let category: String
    let factCount: Int
    let entityCount: Int
    let avgConfidence: Double
    let coverageLevel: String

    enum CodingKeys: String, CodingKey {
        case category
        case factCount = "fact_count"
        case entityCount = "entity_count"
        case avgConfidence = "avg_confidence"
        case coverageLevel = "coverage_level"
    }

    var displayCategory: String {
        category.replacingOccurrences(of: "_", with: " ").capitalized
    }

    var levelColor: String {
        switch coverageLevel {
        case "strong": return "green"
        case "moderate": return "yellow"
        case "sparse": return "orange"
        default: return "red"
        }
    }
}

struct CoverageResponse: Codable {
    let coverage: [CoverageItem]
    let gaps: [CoverageItem]
}

// MARK: - Biography

struct BiographyResponse: Codable {
    let biography: String
    let userName: String

    enum CodingKeys: String, CodingKey {
        case biography
        case userName = "user_name"
    }
}

// MARK: - Health

struct HealthResponse: Codable {
    let status: String
    let conversations: Int
    let messages: Int
    let facts: Int
    let entities: Int
    let relationships: Int
    let vectors: Int
}
