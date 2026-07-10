---
language: typescript
tags: [graphql, apollo, api, server]
title: Apollo Server
description: Schema (typeDefs + resolvers), Query/Mutation types, context for auth, data sources, error handling
source: pattern
---

# Apollo Server

## Setup

```typescript
// npm install @apollo/server graphql
import { ApolloServer } from '@apollo/server';
import { startStandaloneServer } from '@apollo/server/standalone';
```

## Schema (typeDefs)

```typescript
import { gql } from 'graphql-tag';

export const typeDefs = gql`
  # --- Types ---
  type User {
    id: ID!
    email: String!
    name: String!
    role: Role!
    posts: [Post!]
    createdAt: String!
  }

  type Post {
    id: ID!
    title: String!
    content: String!
    published: Boolean!
    author: User!
    createdAt: String!
    updatedAt: String!
  }

  enum Role {
    ADMIN
    MODERATOR
    USER
  }

  # --- Input Types ---
  input CreatePostInput {
    title: String!
    content: String!
    published: Boolean
  }

  input UpdatePostInput {
    title: String
    content: String
    published: Boolean
  }

  input PaginationInput {
    page: Int = 1
    limit: Int = 10
  }

  # --- Queries ---
  type Query {
    "Get a user by ID"
    user(id: ID!): User

    "Get the currently authenticated user"
    me: User

    "List posts with pagination"
    posts(pagination: PaginationInput): [Post!]!

    "Get a single post by ID"
    post(id: ID!): Post

    "Search posts by title"
    searchPosts(query: String!): [Post!]!
  }

  # --- Mutations ---
  type Mutation {
    "Create a new post (requires USER or higher)"
    createPost(input: CreatePostInput!): Post!

    "Update an existing post (author or admin only)"
    updatePost(id: ID!, input: UpdatePostInput!): Post!

    "Delete a post (author or admin only)"
    deletePost(id: ID!): Boolean!

    "Login returns a JWT token"
    login(email: String!, password: String!): AuthPayload!
  }

  type AuthPayload {
    token: String!
    user: User!
  }
`;
```

## Resolvers

```typescript
import { Resolvers } from './generated/graphql'; // or define manually

export const resolvers: Resolvers = {
  Query: {
    user: async (_, { id }, { dataSources }) => {
      return dataSources.userAPI.getUser(id);
    },

    me: async (_, __, { dataSources, user }) => {
      if (!user) throw new AuthenticationError('You must be logged in');
      return dataSources.userAPI.getUser(user.id);
    },

    posts: async (_, { pagination }, { dataSources }) => {
      const { page = 1, limit = 10 } = pagination || {};
      return dataSources.postAPI.getPosts({ page, limit });
    },

    post: async (_, { id }, { dataSources }) => {
      return dataSources.postAPI.getPost(id);
    },

    searchPosts: async (_, { query }, { dataSources }) => {
      return dataSources.postAPI.searchPosts(query);
    },
  },

  Mutation: {
    login: async (_, { email, password }, { dataSources }) => {
      return dataSources.authAPI.login(email, password);
    },

    createPost: async (_, { input }, { dataSources, user }) => {
      if (!user) throw new AuthenticationError('You must be logged in');
      return dataSources.postAPI.createPost({ ...input, authorId: user.id });
    },

    updatePost: async (_, { id, input }, { dataSources, user }) => {
      if (!user) throw new AuthenticationError('You must be logged in');
      const post = await dataSources.postAPI.getPost(id);
      if (post.author.id !== user.id && user.role !== 'ADMIN') {
        throw new ForbiddenError('You can only edit your own posts');
      }
      return dataSources.postAPI.updatePost(id, input);
    },

    deletePost: async (_, { id }, { dataSources, user }) => {
      if (!user) throw new AuthenticationError('You must be logged in');
      const post = await dataSources.postAPI.getPost(id);
      if (post.author.id !== user.id && user.role !== 'ADMIN') {
        throw new ForbiddenError('You can only delete your own posts');
      }
      return dataSources.postAPI.deletePost(id);
    },
  },

  // --- Type resolvers for relationships ---
  Post: {
    author: async (parent, _, { dataSources }) => {
      return dataSources.userAPI.getUser(parent.authorId);
    },
  },

  User: {
    posts: async (parent, _, { dataSources }) => {
      return dataSources.postAPI.getPostsByAuthor(parent.id);
    },
  },
};
```

## Context for Authentication

```typescript
import { ExpressContextFunctionArgument } from '@apollo/server/express4';
import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key';

export interface ContextValue {
  user: { id: string; role: string } | null;
  dataSources: DataSources;
}

export async function createContext({ req }: ExpressContextFunctionArgument): Promise<ContextValue> {
  // Extract token from Authorization header
  const authHeader = req.headers.authorization || '';
  const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : null;

  let user: { id: string; role: string } | null = null;

  if (token) {
    try {
      const decoded = jwt.verify(token, JWT_SECRET) as { id: string; role: string };
      user = decoded;
    } catch (err) {
      // Invalid token — user stays null (public access)
      console.warn('Invalid JWT token:', err);
    }
  }

  return {
    user,
    dataSources: initializeDataSources(),
  };
}
```

## Data Sources

```typescript
import { RESTDataSource } from '@apollo/datasource-rest';
import { DataSourceConfig } from '@apollo/datasource-rest';

// --- REST Data Source ---
class UserAPI extends RESTDataSource {
  constructor() {
    super();
    this.baseURL = process.env.USER_API_URL || 'http://localhost:4001/api/';
  }

  async getUser(id: string): Promise<User> {
    return this.get(`users/${id}`);
  }

  async getUsersByIds(ids: string[]): Promise<User[]> {
    return this.get('users', { params: { ids: ids.join(',') } });
  }
}

class PostAPI extends RESTDataSource {
  constructor() {
    super();
    this.baseURL = process.env.POST_API_URL || 'http://localhost:4002/api/';
  }

  async getPosts({ page, limit }: { page: number; limit: number }): Promise<Post[]> {
    return this.get('posts', { params: { page: String(page), limit: String(limit) } });
  }

  async getPost(id: string): Promise<Post> {
    return this.get(`posts/${id}`);
  }

  async createPost(input: CreatePostInput & { authorId: string }): Promise<Post> {
    return this.post('posts', { body: input });
  }

  async updatePost(id: string, input: UpdatePostInput): Promise<Post> {
    return this.patch(`posts/${id}`, { body: input });
  }

  async deletePost(id: string): Promise<boolean> {
    await this.delete(`posts/${id}`);
    return true;
  }

  async searchPosts(query: string): Promise<Post[]> {
    return this.get('posts/search', { params: { q: query } });
  }

  async getPostsByAuthor(authorId: string): Promise<Post[]> {
    return this.get('posts', { params: { authorId } });
  }
}

// --- In-Memory Data Source (for prototyping) ---
class InMemoryDataSource {
  private users: any[] = [
    { id: '1', email: 'alice@example.com', name: 'Alice', role: 'ADMIN', createdAt: '2024-01-01T00:00:00Z' },
    { id: '2', email: 'bob@example.com', name: 'Bob', role: 'USER', createdAt: '2024-01-02T00:00:00Z' },
  ];

  private posts: any[] = [
    { id: '1', title: 'Hello World', content: 'First post!', published: true, authorId: '1', createdAt: '2024-01-03T00:00:00Z', updatedAt: '2024-01-03T00:00:00Z' },
  ];

  async getUser(id: string) { return this.users.find(u => u.id === id); }
  async getPosts() { return this.posts; }
  async getPost(id: string) { return this.posts.find(p => p.id === id); }
  async createPost(input: any) { const p = { ...input, id: String(this.posts.length + 1), createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }; this.posts.push(p); return p; }
}

// Data sources registry
interface DataSources {
  userAPI: UserAPI;
  postAPI: PostAPI;
}

function initializeDataSources(): DataSources {
  return {
    userAPI: new UserAPI(),
    postAPI: new PostAPI(),
  };
}
```

## Error Handling

```typescript
import {
  ApolloServerErrorCode,
  unwrapResolverError,
} from '@apollo/server/errors';
import { GraphQLError } from 'graphql';
import { ApolloServer } from '@apollo/server';

// Custom error codes
export const ErrorCode = {
  ...ApolloServerErrorCode,
  FORBIDDEN: 'FORBIDDEN',
  NOT_FOUND: 'NOT_FOUND',
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  RATE_LIMITED: 'RATE_LIMITED',
};

// Custom error classes
export class NotFoundError extends GraphQLError {
  constructor(message: string) {
    super(message, {
      extensions: { code: ErrorCode.NOT_FOUND, http: { status: 404 } },
    });
  }
}

export class ForbiddenError extends GraphQLError {
  constructor(message: string) {
    super(message, {
      extensions: { code: ErrorCode.FORBIDDEN, http: { status: 403 } },
    });
  }
}

export class ValidationError extends GraphQLError {
  constructor(message: string, fields?: Record<string, string>) {
    super(message, {
      extensions: { code: ErrorCode.VALIDATION_ERROR, fields, http: { status: 400 } },
    });
  }
}

export class AuthenticationError extends GraphQLError {
  constructor(message: string = 'Authentication required') {
    super(message, {
      extensions: { code: 'UNAUTHENTICATED', http: { status: 401 } },
    });
  }
}
```

## Server Initialization

```typescript
import { ApolloServer } from '@apollo/server';
import { startStandaloneServer } from '@apollo/server/standalone';

// Create the server
const server = new ApolloServer<ContextValue>({
  typeDefs,
  resolvers,
  // Format errors to hide internal details in production
  formatError: (formattedError, error) => {
    // Don't expose internal error details to clients
    if (formattedError.extensions?.code === 'INTERNAL_SERVER_ERROR') {
      return { message: 'Internal server error', extensions: { code: 'INTERNAL_SERVER_ERROR' } };
    }
    return formattedError;
  },
  // Enable introspection in development only
  introspection: process.env.NODE_ENV !== 'production',
});

// Start the server
async function startServer() {
  const { url } = await startStandaloneServer(server, {
    context: createContext,
    listen: { port: 4000 },
  });

  console.log(`🚀 Apollo Server ready at: ${url}`);
  console.log(`📊 GraphQL Playground: ${url}graphql`);
}

startServer().catch(console.error);
```

## Full Example Queries

```graphql
# --- Query with variables ---
query GetUser($userId: ID!) {
  user(id: $userId) {
    id
    name
    email
    posts {
      title
      content
    }
  }
}

# Variables:
# { "userId": "1" }

# --- Mutation with variables ---
mutation CreateNewPost($input: CreatePostInput!) {
  createPost(input: $input) {
    id
    title
    published
    createdAt
  }
}

# Variables:
# { "input": { "title": "New Post", "content": "My content", "published": true } }

# --- Login mutation ---
mutation Login($email: String!, $password: String!) {
  login(email: $email, password: $password) {
    token
    user {
      id
      name
      role
    }
  }
}

# Variables:
# { "email": "alice@example.com", "password": "secret123" }
```