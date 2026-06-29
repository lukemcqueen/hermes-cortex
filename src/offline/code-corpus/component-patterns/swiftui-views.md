---
language: swift
tags: [swiftui, ios, views, apple]
title: SwiftUI View Composition
description: "@State, @Binding, @ObservedObject, ViewBuilder, modifiers, preferenceKey"
source: pattern
---

## @State and @Binding

```swift
import SwiftUI

// MARK: - Counter with @State (local state)
struct CounterView: View {
    @State private var count: Int = 0
    @State private var step: Int = 1
    
    var body: some View {
        VStack(spacing: 16) {
            Text("\(count)")
                .font(.system(size: 64, weight: .bold, design: .monospaced))
                .foregroundColor(count >= 0 ? .primary : .red)
                .contentTransition(.numericText())
            
            HStack(spacing: 12) {
                actionButton("−\(step)", color: .red) { count -= step }
                actionButton("Reset", color: .gray) { count = 0 }
                actionButton("+\(step)", color: .green) { count += step }
            }
            
            Stepper("Step: \(step)", value: $step, in: 1...10)
        }
        .padding()
        .animation(.spring(response: 0.3), value: count)
    }
    
    private func actionButton(_ label: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .fontWeight(.semibold)
                .frame(minWidth: 60)
                .padding(.vertical, 8)
                .padding(.horizontal, 16)
                .background(color.opacity(0.15))
                .clipShape(Capsule())
        }
    }
}

// MARK: - @Binding (child modifies parent state)
struct EditableTextField: View {
    let label: String
    @Binding var text: String
    var validator: ((String) -> String?)? = nil
    
    @State private var errorMessage: String? = nil
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
            
            TextField(label, text: $text)
                .textFieldStyle(.roundedBorder)
                .onChange(of: text) { _, newValue in
                    errorMessage = validator?(newValue)
                }
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(errorMessage != nil ? Color.red : Color.clear, lineWidth: 1)
                )
            
            if let error = errorMessage {
                Text(error)
                    .font(.caption2)
                    .foregroundColor(.red)
            }
        }
    }
}

struct ProfileEditor: View {
    @State private var name: String = ""
    @State private var email: String = ""
    
    var body: some View {
        Form {
            Section("Personal Info") {
                EditableTextField(
                    label: "Name",
                    text: $name,
                    validator: { $0.isEmpty ? "Name is required" : nil }
                )
                EditableTextField(
                    label: "Email",
                    text: $email,
                    validator: { $0.contains("@") ? nil : "Invalid email" }
                )
            }
            
            Section {
                Button("Save") {
                    print("Saving: \(name), \(email)")
                }
                .disabled(name.isEmpty || !email.contains("@"))
            }
        }
        .padding()
    }
}
```

## @ObservedObject / @StateObject (Observable Models)

```swift
import SwiftUI
import Observation

// MARK: - Observable model (iOS 17+ @Observable macro)
@Observable
class TaskStore {
    var tasks: [TaskItem] = []
    var filterText: String = ""
    var isLoading: Bool = false
    
    var filteredTasks: [TaskItem] {
        if filterText.isEmpty { return tasks }
        return tasks.filter { $0.title.localizedCaseInsensitiveContains(filterText) }
    }
    
    var completedCount: Int { tasks.filter(\.isCompleted).count }
    var pendingCount: Int { tasks.count - completedCount }
    
    func loadTasks() async {
        isLoading = true
        // Simulate network fetch
        try? await Task.sleep(nanoseconds: 500_000_000)
        tasks = TaskItem.samples
        isLoading = false
    }
    
    func toggleTask(_ task: TaskItem) {
        if let index = tasks.firstIndex(where: { $0.id == task.id }) {
            tasks[index].isCompleted.toggle()
        }
    }
    
    func deleteTasks(at offsets: IndexSet) {
        tasks.remove(atOffsets: offsets)
    }
}

struct TaskItem: Identifiable, Hashable {
    let id: UUID
    var title: String
    var isCompleted: Bool
    var priority: Priority
    var dueDate: Date?
    
    enum Priority: String, CaseIterable {
        case low, medium, high
    }
    
    static let samples: [TaskItem] = [
        TaskItem(id: UUID(), title: "Review PR #42", isCompleted: false, priority: .high, dueDate: Date().addingTimeInterval(86400)),
        TaskItem(id: UUID(), title: "Write documentation", isCompleted: false, priority: .medium, dueDate: Date().addingTimeInterval(172800)),
        TaskItem(id: UUID(), title: "Fix login bug", isCompleted: true, priority: .high, dueDate: Date().addingTimeInterval(-3600)),
        TaskItem(id: UUID(), title: "Update dependencies", isCompleted: false, priority: .low, dueDate: nil),
    ]
}

// MARK: - Task Row View
struct TaskRowView: View {
    let task: TaskItem
    let onToggle: () -> Void
    
    var body: some View {
        HStack(spacing: 12) {
            Button(action: onToggle) {
                Image(systemName: task.isCompleted ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(task.isCompleted ? .green : .secondary)
                    .font(.title3)
            }
            .buttonStyle(.plain)
            
            VStack(alignment: .leading, spacing: 2) {
                Text(task.title)
                    .strikethrough(task.isCompleted)
                    .foregroundColor(task.isCompleted ? .secondary : .primary)
                    .fontWeight(task.priority == .high && !task.isCompleted ? .semibold : .regular)
                
                if let dueDate = task.dueDate {
                    Text(dueDate, style: .date)
                        .font(.caption)
                        .foregroundColor(dueDate < Date() && !task.isCompleted ? .red : .secondary)
                }
            }
            
            Spacer()
            
            PriorityBadge(priority: task.priority)
        }
        .padding(.vertical, 4)
    }
}

struct PriorityBadge: View {
    let priority: TaskItem.Priority
    
    var color: Color {
        switch priority {
        case .low: return .gray
        case .medium: return .orange
        case .high: return .red
        }
    }
    
    var body: some View {
        Text(priority.rawValue.uppercased())
            .font(.caption2)
            .fontWeight(.bold)
            .foregroundColor(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.12))
            .clipShape(Capsule())
    }
}

// MARK: - Main List View
struct TaskListView: View {
    @StateObject private var store = TaskStore()  // @StateObject: creates and owns the model
    @State private var showCompleted: Bool = true
    @State private var sortBy: TaskItem.Priority? = nil
    
    var body: some View {
        NavigationStack {
            List {
                if store.isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                }
                
                ForEach(displayedTasks) { task in
                    TaskRowView(task: task) {
                        withAnimation(.spring(response: 0.3)) {
                            store.toggleTask(task)
                        }
                    }
                }
                .onDelete(perform: store.deleteTasks)
            }
            .searchable(text: $store.filterText, prompt: "Filter tasks")
            .navigationTitle("Tasks")
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Picker("Sort", selection: $sortBy) {
                        Text("All").tag(nil as TaskItem.Priority?)
                        ForEach(TaskItem.Priority.allCases, id: \.self) { p in
                            Text(p.rawValue.capitalized).tag(p as TaskItem.Priority?)
                        }
                    }
                    
                    Toggle("Show completed", isOn: $showCompleted)
                        .toggleStyle(.button)
                        .symbolVariant(showCompleted ? .fill : .none)
                }
            }
            .task { await store.loadTasks() }
            .overlay(alignment: .bottom) {
                HStack {
                    Text("\(store.pendingCount) pending, \(store.completedCount) done")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.bottom, 8)
            }
        }
    }
    
    private var displayedTasks: [TaskItem] {
        var result = store.filteredTasks
        if !showCompleted { result = result.filter { !$0.isCompleted } }
        if let sortBy = sortBy { result = result.filter { $0.priority == sortBy } }
        return result
    }
}
```

## ViewBuilder / Function Builders

```swift
import SwiftUI

// MARK: - Generic Card with @ViewBuilder content
struct Card<Content: View>: View {
    let title: String
    let content: Content
    var accentColor: Color = .blue
    var collapsed: Bool = false
    
    init(
        title: String,
        accentColor: Color = .blue,
        collapsed: Bool = false,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.accentColor = accentColor
        self.collapsed = collapsed
        self.content = content()
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(title)
                    .font(.headline)
                    .foregroundColor(accentColor)
                Spacer()
            }
            .padding()
            .background(accentColor.opacity(0.08))
            
            if !collapsed {
                content
                    .padding()
            }
        }
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.06), radius: 4, y: 2)
    }
}

// MARK: - Conditional view builder
struct LoadableContent<Value, Content: View>: View where Value: Sendable {
    let state: AsyncState<Value>
    let content: (Value) -> Content
    
    enum AsyncState<T> {
        case idle
        case loading
        case success(T)
        case failure(Error)
    }
    
    init(
        _ state: AsyncState<Value>,
        @ViewBuilder content: @escaping (Value) -> Content
    ) {
        self.state = state
        self.content = content
    }
    
    var body: some View {
        switch state {
        case .idle:
            Color.clear
        case .loading:
            ProgressView()
                .frame(maxWidth: .infinity, minHeight: 100)
        case .success(let value):
            content(value)
        case .failure(let error):
            VStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.largeTitle)
                    .foregroundColor(.orange)
                Text(error.localizedDescription)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity, minHeight: 100)
        }
    }
}

// Usage of @ViewBuilder
struct DashboardView: View {
    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                Card(title: "Welcome", accentColor: .green) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Hello, SwiftUI!")
                            .font(.title2)
                            .fontWeight(.bold)
                        Text("This card uses @ViewBuilder to compose content inline.")
                            .font(.body)
                            .foregroundColor(.secondary)
                    }
                }
                
                Card(title: "Analytics", collapsed: true) {
                    LoadableContent(.success([42, 73, 91, 55])) { values in
                        ChartView(values: values)
                    }
                }
            }
            .padding()
        }
    }
}

struct ChartView: View {
    let values: [Int]
    
    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            ForEach(Array(values.enumerated()), id: \.offset) { index, value in
                VStack {
                    Text("\(value)")
                        .font(.caption2)
                    Rectangle()
                        .fill(Color.blue.gradient)
                        .frame(width: 30, height: CGFloat(value))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                }
            }
        }
        .frame(height: 120)
    }
}
```

## View Modifiers and PreferenceKey

```swift
import SwiftUI

// MARK: - Custom View Modifier
struct CardStyle: ViewModifier {
    let cornerRadius: CGFloat
    let shadowRadius: CGFloat
    
    func body(content: Content) -> some View {
        content
            .background(Color(.systemBackground))
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .shadow(color: .black.opacity(0.08), radius: shadowRadius, y: 2)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(Color.secondary.opacity(0.1), lineWidth: 1)
            )
    }
}

extension View {
    func cardStyle(cornerRadius: CGFloat = 12, shadowRadius: CGFloat = 4) -> some View {
        modifier(CardStyle(cornerRadius: cornerRadius, shadowRadius: shadowRadius))
    }
}

// MARK: - PreferenceKey (child → parent communication)
struct TabHeightPreferenceKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

struct TabBarHeightKey: PreferenceKey {
    static let defaultValue: [Int: CGFloat] = [:]
    
    static func reduce(value: inout [Int: CGFloat], nextValue: () -> [Int: CGFloat]) {
        value.merge(nextValue()) { $1 }
    }
}

// MARK: - Child view reporting its height
struct MeasuredTab<Content: View>: View {
    let index: Int
    let content: Content
    
    init(index: Int, @ViewBuilder content: () -> Content) {
        self.index = index
        self.content = content()
    }
    
    var body: some View {
        content
            .background(
                GeometryReader { proxy in
                    Color.clear
                        .preference(
                            key: TabBarHeightKey.self,
                            value: [index: proxy.size.height]
                        )
                }
            )
    }
}

// MARK: - Tab bar that auto-sizes based on content
struct AutoSizingTabView<Content: View>: View {
    @State private var tabHeights: [Int: CGFloat] = [:]
    @State private var selectedTab: Int = 0
    let content: Content
    
    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Tab bar
            HStack(spacing: 0) {
                ForEach(Array(tabHeights.keys.sorted()), id: \.self) { index in
                    Button(action: { selectedTab = index }) {
                        Text("Tab \(index + 1)")
                            .fontWeight(selectedTab == index ? .bold : .regular)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(selectedTab == index ? Color.blue.opacity(0.1) : Color.clear)
                    }
                    .buttonStyle(.plain)
                }
            }
            .background(Color(.systemGray6))
            
            // Content with dynamic height
            Group {
                if let height = tabHeights[selectedTab] {
                    content
                        .frame(height: height)
                        .animation(.spring(response: 0.35), value: height)
                } else {
                    content
                }
            }
            .onPreferenceChange(TabBarHeightKey.self) { heights in
                tabHeights = heights
            }
        }
    }
}

// Usage
struct ModifiersAndPreferencesDemo: View {
    var body: some View {
        AutoSizingTabView {
            MeasuredTab(index: 0) {
                VStack(spacing: 12) {
                    Text("Short content")
                        .font(.title)
                    Text("This tab has minimal content.")
                        .foregroundColor(.secondary)
                }
                .padding()
                .cardStyle()
            }
            
            MeasuredTab(index: 1) {
                VStack(spacing: 12) {
                    Text("Longer content")
                        .font(.title)
                    ForEach(1...5, id: \.self) { i in
                        Text("Row \(i)")
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal)
                    }
                }
                .padding()
                .cardStyle()
            }
        }
        .padding()
    }
}
```