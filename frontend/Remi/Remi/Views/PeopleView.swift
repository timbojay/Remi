import SwiftUI

struct PeopleView: View {
    @State private var people: [Entity] = []
    @State private var isLoading = true
    private let apiClient = APIClient()

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading...")
            } else if people.isEmpty {
                ContentUnavailableView(
                    "No People Yet",
                    systemImage: "person.3",
                    description: Text("People will appear here as you share your story.")
                )
            } else {
                List(people) { person in
                    HStack(spacing: 12) {
                        Image(systemName: person.icon)
                            .foregroundStyle(.blue)
                            .frame(width: 24)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(person.name)
                                .font(.headline)
                            if let role = person.familyRole, !role.isEmpty {
                                Text(role.capitalized)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            if let desc = person.description, !desc.isEmpty {
                                Text(desc)
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                                    .lineLimit(2)
                            }
                        }
                        Spacer()
                        if person.isVerified == 1 {
                            Image(systemName: "checkmark.seal.fill")
                                .foregroundStyle(.green)
                                .font(.caption)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .navigationTitle("People")
        .task { await loadPeople() }
        .refreshable { await loadPeople() }
    }

    private func loadPeople() async {
        isLoading = true
        people = await apiClient.getEntities(type: "person")
        isLoading = false
    }
}
