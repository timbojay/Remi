import SwiftUI

struct SidebarView: View {
    @Binding var conversations: [ConversationSummary]
    @Binding var selectedId: String?
    let onNewChat: () -> Void
    let onRefresh: () async -> Void

    var body: some View {
        List(selection: $selectedId) {
            ForEach(conversations) { conv in
                VStack(alignment: .leading, spacing: 4) {
                    Text(conv.displayTitle)
                        .font(.body)
                        .lineLimit(1)
                    Text(conv.displayDate)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 2)
                .tag(conv.id)
            }
        }
        .listStyle(.sidebar)
        .toolbar {
            ToolbarItem {
                Button(action: onNewChat) {
                    Image(systemName: "square.and.pencil")
                }
                .help("New conversation")
            }
        }
        .task {
            await onRefresh()
        }
    }
}
