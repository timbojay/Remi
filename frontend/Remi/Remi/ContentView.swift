import SwiftUI

enum SidebarItem: Hashable {
    case chat
    case people
    case facts
    case timeline
    case familyTree
    case biography
    case coverage

    var label: String {
        switch self {
        case .chat: "Chat"
        case .people: "People"
        case .facts: "Facts"
        case .timeline: "Timeline"
        case .familyTree: "Family Tree"
        case .biography: "Biography"
        case .coverage: "Coverage"
        }
    }

    var icon: String {
        switch self {
        case .chat: "bubble.left.and.bubble.right"
        case .people: "person.2"
        case .facts: "list.bullet.rectangle"
        case .timeline: "calendar.day.timeline.left"
        case .familyTree: "figure.2.and.child.holdinghands"
        case .biography: "book"
        case .coverage: "chart.bar"
        }
    }
}

struct ContentView: View {
    @State private var viewModel = ChatViewModel()
    @State private var selectedSection: SidebarItem? = .chat

    var body: some View {
        NavigationSplitView {
            List(selection: $selectedSection) {
                Section("Interview") {
                    Label(SidebarItem.chat.label, systemImage: SidebarItem.chat.icon)
                        .tag(SidebarItem.chat)
                }

                Section("Knowledge") {
                    Label(SidebarItem.people.label, systemImage: SidebarItem.people.icon)
                        .tag(SidebarItem.people)
                    Label(SidebarItem.facts.label, systemImage: SidebarItem.facts.icon)
                        .tag(SidebarItem.facts)
                    Label(SidebarItem.timeline.label, systemImage: SidebarItem.timeline.icon)
                        .tag(SidebarItem.timeline)
                    Label(SidebarItem.familyTree.label, systemImage: SidebarItem.familyTree.icon)
                        .tag(SidebarItem.familyTree)
                }

                Section("Output") {
                    Label(SidebarItem.biography.label, systemImage: SidebarItem.biography.icon)
                        .tag(SidebarItem.biography)
                    Label(SidebarItem.coverage.label, systemImage: SidebarItem.coverage.icon)
                        .tag(SidebarItem.coverage)
                }

                if selectedSection == .chat {
                    Section("Conversations") {
                        ForEach(viewModel.conversations) { conv in
                            Button {
                                viewModel.selectedConversationId = conv.id
                            } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(conv.displayTitle)
                                        .font(.body)
                                        .lineLimit(1)
                                        .foregroundStyle(
                                            viewModel.selectedConversationId == conv.id
                                                ? Color.accentColor : .primary
                                        )
                                    Text(conv.displayDate)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(.vertical, 2)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .listStyle(.sidebar)
            .navigationTitle("Remi")
            #if os(macOS)
            .navigationSplitViewColumnWidth(min: 200, ideal: 250)
            #endif
            .toolbar {
                ToolbarItem {
                    Button {
                        selectedSection = .chat
                        viewModel.startNewConversation()
                    } label: {
                        Image(systemName: "square.and.pencil")
                    }
                    .help("New conversation")
                }
            }
        } detail: {
            detailView
        }
        .onChange(of: viewModel.selectedConversationId) { _, newValue in
            Task {
                await viewModel.selectConversation(id: newValue)
            }
        }
        .task {
            await viewModel.checkBackendHealth()
            await viewModel.loadConversations()
        }
    }

    @ViewBuilder
    private var detailView: some View {
        switch selectedSection {
        case .chat:
            ChatView(viewModel: viewModel)
        case .people:
            PeopleView()
        case .facts:
            FactsView()
        case .timeline:
            TimelineView()
        case .familyTree:
            FamilyTreeView()
        case .biography:
            BiographyView()
        case .coverage:
            CoverageView()
        case nil:
            Text("Select a section")
                .font(.title2)
                .foregroundStyle(.secondary)
        }
    }
}
