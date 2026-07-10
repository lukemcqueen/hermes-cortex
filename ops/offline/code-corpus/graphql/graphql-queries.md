---
language: typescript
tags: [graphql, queries, mutations, subscriptions]
title: GraphQL Query Patterns
description: Fragments, variables, directives, pagination (connection spec), mutations with optimistic update, subscriptions
source: pattern
---

# GraphQL Query Patterns

## Fragments

```graphql
# --- Reusable fragments ---
fragment UserFields on User {
  id
  name
  email
  avatarUrl
}

fragment PostFields on Post {
  id
  title
  excerpt
  createdAt
  author {
    ...UserFields
  }
}

# --- Using fragments in queries ---
query GetFeed {
  feed {
    ...PostFields
    comments {
      id
      text
      author {
        ...UserFields
      }
    }
  }
}

# --- Inline fragments for interfaces/unions ---
query GetSearchResults {
  search(query: "graphql") {
    ... on User {
      ...UserFields
      bio
    }
    ... on Post {
      ...PostFields
      content
    }
    ... on Comment {
      id
      text
    }
  }
}

# --- Fragment spreads with @defer (Apollo Client) ---
query GetPostWithComments($postId: ID!) {
  post(id: $postId) {
    ...PostFields
    ...SlowComments @defer
  }
}

fragment SlowComments on Post {
  comments {
    id
    text
    author {
      name
    }
  }
}
```

## Variables

```graphql
# --- Query with variable definitions ---
query GetUserPosts($userId: ID!, $pagination: PaginationInput, $includeDrafts: Boolean) {
  user(id: $userId) {
    ...UserFields
    posts(pagination: $pagination, includeDrafts: $includeDrafts) {
      ...PostFields
    }
  }
}

# Variables JSON:
{
  "userId": "abc-123",
  "pagination": { "page": 1, "limit": 10 },
  "includeDrafts": false
}

# --- Mutation with variables ---
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ...PostFields
  }
}

# Variables:
{
  "input": {
    "title": "My New Post",
    "content": "This is the content",
    "published": true
  }
}

# --- Default values ---
query GetPosts($limit: Int = 20, $offset: Int = 0) {
  posts(limit: $limit, offset: $offset) {
    id
    title
  }
}
```

## Directives (@include, @skip)

```graphql
# --- @include: Only include field if condition is true ---
query GetProfile($showEmail: Boolean!, $showPosts: Boolean!) {
  me {
    id
    name
    email @include(if: $showEmail)
    bio
    posts @include(if: $showPosts) {
      id
      title
    }
  }
}

# Variables: { "showEmail": true, "showPosts": false }
# Result includes email, excludes posts

# --- @skip: Skip field if condition is true ---
query GetUser($hideSensitive: Boolean!) {
  user(id: "1") {
    id
    name
    email @skip(if: $hideSensitive)
    ssn @skip(if: true)  # Always hidden
  }
}

# --- @deprecated: Mark fields as deprecated in schema ---
# Schema side:
# type User {
#   id: ID!
#   name: String!
#   oldField: String @deprecated(reason: "Use 'newField' instead")
#   newField: String!
# }

# --- @specifiedBy: Custom scalar directive ---
# scalar JSON @specifiedBy(url: "https://tools.ietf.org/html/rfc8259")

# --- Custom directives (server-side) ---
# @auth(requires: Role) — authentication
# @rateLimit(max: Int, window: String) — rate limiting
# @upper — transform string to uppercase
```

## Pagination (Relay Connection Spec)

```graphql
# --- Connection types (schema definition) ---
"""
Connection spec provides cursor-based pagination.
Each edge has a cursor (opaque string) and a node (the actual data).
"""
type PostConnection {
  edges: [PostEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type PostEdge {
  cursor: String!
  node: Post!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}

# --- Query with connection pagination ---
query GetPaginatedPosts($first: Int, $after: String, $last: Int, $before: String) {
  posts(first: $first, after: $after, last: $last, before: $before) {
    totalCount
    edges {
      cursor
      node {
        id
        title
        excerpt
        createdAt
      }
    }
    pageInfo {
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }
  }
}

# Variables — forward pagination (first 10 after cursor):
# { "first": 10, "after": "YXJyYXljb25uZWN0aW9uOjE5" }

# Variables — backward pagination (last 10 before cursor):
# { "last": 10, "before": "YXJyYXljb25uZWN0aW9uOjMw" }

# --- Relay-style pagination helper query ---
query GetPostsPaginated {
  posts(first: 5) {
    edges {
      cursor
      node {
        id
        title
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}

# Load more with: { "first": 5, "after": endCursor }
```

## Mutations with Optimistic Update (Apollo Client)

```typescript
// --- Apollo Client mutation with optimistic update ---
import { gql, useMutation } from '@apollo/client';
import { v4 as uuidv4 } from 'uuid';

const CREATE_POST = gql`
  mutation CreatePost($input: CreatePostInput!) {
    createPost(input: $input) {
      id
      title
      content
      published
      createdAt
      author {
        id
        name
      }
    }
  }
`;

// React component
function CreatePostForm() {
  const [createPost, { loading, error }] = useMutation(CREATE_POST, {
    // Optimistic update — immediately update the cache
    update: (cache, { data }) => {
      if (!data?.createPost) return;

      // Read existing posts from cache
      const existingPosts = cache.readQuery({
        query: GET_POSTS,
        variables: { first: 10 },
      });

      if (existingPosts) {
        cache.writeQuery({
          query: GET_POSTS,
          variables: { first: 10 },
          data: {
            posts: {
              ...existingPosts.posts,
              edges: [
                {
                  __typename: 'PostEdge',
                  cursor: Buffer.from(`arrayconnection:${data.createPost.id}`).toString('base64'),
                  node: data.createPost,
                },
                ...existingPosts.posts.edges,
              ],
            },
          },
        });
      }
    },
    // Refetch queries after mutation succeeds
    refetchQueries: [{ query: GET_POST_COUNT }],
    // Optimistic response shown immediately
    optimisticResponse: {
      createPost: {
        __typename: 'Post',
        id: `optimistic-${uuidv4()}`,
        title: 'Loading...',
        content: '...',
        published: true,
        createdAt: new Date().toISOString(),
        author: {
          __typename: 'User',
          id: 'current-user-id',
          name: 'Current User',
        },
      },
    },
    // Roll back optimistic update on error
    onError: (err) => {
      console.error('Failed to create post:', err);
      // Apollo automatically rolls back the optimistic update
    },
  });

  const handleSubmit = async (formData: any) => {
    try {
      const { data } = await createPost({
        variables: {
          input: {
            title: formData.title,
            content: formData.content,
            published: true,
          },
        },
      });
      console.log('Post created:', data?.createPost);
    } catch (err) {
      // Error handled by onError above
    }
  };

  // ... render form
}

// --- Optimistic update for likes ---
const TOGGLE_LIKE = gql`
  mutation ToggleLike($postId: ID!) {
    toggleLike(postId: $postId) {
      id
      likedByMe
      likeCount
    }
  }
`;

function LikeButton({ postId, likedByMe, likeCount }: Props) {
  const [toggleLike] = useMutation(TOGGLE_LIKE, {
    variables: { postId },
    optimisticResponse: {
      toggleLike: {
        __typename: 'Post',
        id: postId,
        likedByMe: !likedByMe,
        likeCount: likedByMe ? likeCount - 1 : likeCount + 1,
      },
    },
  });

  return (
    <button onClick={() => toggleLike()}>
      {likedByMe ? '❤️' : '🤍'} {likeCount}
    </button>
  );
}
```

## Subscriptions

```graphql
# --- Subscription definition (schema side) ---
type Subscription {
  "Real-time updates when a new post is created"
  postCreated: Post!

  "Real-time updates when a post is updated"
  postUpdated: Post!

  "Real-time notifications for the current user"
  notification(userId: ID!): Notification!

  "Real-time like count changes"
  likeCountChanged(postId: ID!): LikeCountPayload!
}

type Notification {
  id: ID!
  type: NotificationType!
  message: String!
  createdAt: String!
}

enum NotificationType {
  NEW_FOLLOWER
  NEW_LIKE
  NEW_COMMENT
  MENTION
}

type LikeCountPayload {
  postId: ID!
  likeCount: Int!
}

# --- Client-side subscription (Apollo Client) ---
import { gql, useSubscription } from '@apollo/client';

const POST_CREATED = gql`
  subscription OnPostCreated {
    postCreated {
      id
      title
      excerpt
      author {
        id
        name
      }
      createdAt
    }
  }
`;

function LiveFeed() {
  const { data, loading, error } = useSubscription(POST_CREATED, {
    // Called every time a new post is created
    onData: ({ data }) => {
      console.log('New post:', data.data?.postCreated);
      // Optionally update cache or show toast
    },
    onError: (err) => {
      console.error('Subscription error:', err);
    },
  });

  if (loading) return <p>Connecting to live feed...</p>;
  if (error) return <p>Subscription error: {error.message}</p>;

  return data?.postCreated ? (
    <div className="live-post">
      <h3>{data.postCreated.title}</h3>
      <p>by {data.postCreated.author.name}</p>
    </div>
  ) : null;
}

# --- Subscription with variables ---
const USER_NOTIFICATIONS = gql`
  subscription OnUserNotification($userId: ID!) {
    notification(userId: $userId) {
      id
      type
      message
      createdAt
    }
  }
`;

function NotificationListener({ userId }: { userId: string }) {
  const { data } = useSubscription(USER_NOTIFICATIONS, {
    variables: { userId },
    // Reconnect if connection drops
    shouldResubscribe: true,
  });

  useEffect(() => {
    if (data?.notification) {
      showNotification(data.notification);
    }
  }, [data]);

  return null;
}

# --- WebSocket connection setup (Apollo Client) ---
import { GraphQLWsLink } from '@apollo/client/link/subscriptions';
import { createClient } from 'graphql-ws';

const wsLink = new GraphQLWsLink(
  createClient({
    url: 'ws://localhost:4000/graphql',
    connectionParams: {
      authToken: 'bearer-token-here',
    },
    // Reconnect on disconnect
    retryAttempts: 10,
    shouldRetry: () => true,
    on: {
      connected: () => console.log('WebSocket connected'),
      disconnected: (err) => console.log('WebSocket disconnected', err),
      error: (err) => console.error('WebSocket error', err),
    },
  })
);
```

## Full Query Patterns Summary

```graphql
# --- Batch queries in a single request ---
query HomePageData($userId: ID!) {
  # Multiple root fields in one query
  me {
    ...UserFields
  }
  feed(first: 20) {
    edges {
      node {
        ...PostFields
      }
    }
  }
  notifications(userId: $userId, first: 5) {
    edges {
      node {
        id
        message
        type
      }
    }
  }
}

# --- Aliased queries ---
query CompareUsers {
  alice: user(id: "1") {
    ...UserFields
  }
  bob: user(id: "2") {
    ...UserFields
  }
}

# Returns:
# {
#   "alice": { "id": "1", "name": "Alice", ... },
#   "bob": { "id": "2", "name": "Bob", ... }
# }

# --- Nested mutations in order ---
mutation CreatePostAndComment {
  createPost(input: { title: "New", content: "Content" }) {
    id
    title
  }
  addComment(postId: "1", text: "Great post!") {
    id
    text
  }
}
```