import SwiftUI

struct FamilyTreeView: View {
    @State private var tree: FamilyTreeResponse?
    @State private var isLoading = true
    private let apiClient = APIClient()

    private let roleOrder = ["self", "spouse", "parent", "father", "mother", "sibling", "child", "grandparent", "brother-in-law", "sister-in-law", "other"]

    private var sortedRoles: [(String, [FamilyRolePerson])] {
        guard let tree else { return [] }
        return tree.byRole.sorted { a, b in
            let aIdx = roleOrder.firstIndex(of: a.key) ?? roleOrder.count
            let bIdx = roleOrder.firstIndex(of: b.key) ?? roleOrder.count
            return aIdx < bIdx
        }
    }

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading...")
            } else if tree == nil || tree?.people.isEmpty == true {
                ContentUnavailableView(
                    "No Family Data Yet",
                    systemImage: "figure.2.and.child.holdinghands",
                    description: Text("Family relationships will appear here as you share about your family.")
                )
            } else {
                List {
                    ForEach(sortedRoles, id: \.0) { role, people in
                        Section(header: Text(roleDisplayName(role))) {
                            ForEach(people) { person in
                                HStack(spacing: 12) {
                                    Image(systemName: roleIcon(role))
                                        .foregroundStyle(.blue)
                                        .frame(width: 24)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(person.name)
                                            .font(.headline)
                                        if let desc = person.description, !desc.isEmpty {
                                            Text(desc)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                }
                                .padding(.vertical, 2)
                            }
                        }
                    }

                    if let tree, !tree.relationships.isEmpty {
                        Section(header: Text("Connections")) {
                            ForEach(tree.relationships.indices, id: \.self) { idx in
                                let rel = tree.relationships[idx]
                                let fromName = tree.people.first { $0.id == rel.fromEntityId }?.name ?? "?"
                                let toName = tree.people.first { $0.id == rel.toEntityId }?.name ?? "?"
                                HStack {
                                    Text(fromName)
                                        .fontWeight(.medium)
                                    Image(systemName: rel.isBidirectional == 1 ? "arrow.left.arrow.right" : "arrow.right")
                                        .foregroundStyle(.secondary)
                                        .font(.caption)
                                    Text(toName)
                                        .fontWeight(.medium)
                                    Spacer()
                                    Text(rel.relationshipType.replacingOccurrences(of: "_", with: " "))
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Family Tree")
        .task { await loadTree() }
        .refreshable { await loadTree() }
    }

    private func loadTree() async {
        isLoading = true
        tree = await apiClient.getFamilyTree()
        isLoading = false
    }

    private func roleDisplayName(_ role: String) -> String {
        switch role {
        case "self": return "You"
        case "parent", "father", "mother": return "Parents"
        case "sibling": return "Siblings"
        case "spouse": return "Spouse"
        case "child": return "Children"
        case "grandparent": return "Grandparents"
        default: return role.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func roleIcon(_ role: String) -> String {
        switch role {
        case "self": return "person.fill"
        case "parent", "father", "mother": return "figure.stand"
        case "sibling": return "person.2.fill"
        case "spouse": return "heart.fill"
        case "child": return "figure.and.child.holdinghands"
        case "grandparent": return "figure.stand.line.dotted.figure.stand"
        default: return "person"
        }
    }
}
