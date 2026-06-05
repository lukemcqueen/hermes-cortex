---
language: ruby
tags: [testing, pattern]
title: Testing with RSpec
description: RSpec: describe/it/expect, let/subject, context, mocks/doubles, shared_examples.
source: pattern
---

```ruby
# == Basic RSpec structure ==
# spec/user_spec.rb
# require 'rails_helper' (or 'spec_helper')

# RSpec.describe User do
#   describe 'validations' do
#     subject { User.new(name: 'Alice', email: 'alice@example.com') }
#
#     it { is_expected.to be_valid }
#
#     it 'is invalid without an email' do
#       subject.email = nil
#       expect(subject).not_to be_valid
#       expect(subject.errors[:email]).to include("can't be blank")
#     end
#   end
#
#   describe '#full_name' do
#     let(:user) { User.new(first_name: 'Alice', last_name: 'Smith') }
#
#     it 'joins first and last name' do
#       expect(user.full_name).to eq 'Alice Smith'
#     end
#   end
# end

# --- let / subject ---
RSpec.describe Array do
  subject(:array) { [3, 1, 2] }

  describe '#sort' do
    it 'returns a sorted array' do
      expect(array.sort).to eq [1, 2, 3]
    end

    it 'does not modify the original' do
      expect { array.sort }.not_to change(array, :itself)
    end
  end
end

# --- context ---
RSpec.describe 'String' do
  context 'when empty' do
    it 'is empty' do
      expect(''.empty?).to be true
    end
  end

  context 'when not empty' do
    it 'is not empty' do
      expect('hello'.empty?).to be false
    end
  end
end

# --- Mocks / Doubles ---
RSpec.describe 'Mocks' do
  it 'uses a test double' do
    notifier = double('Notifier')
    expect(notifier).to receive(:send).
      with('Hello').
      and_return(true)

    service = NotificationService.new(notifier)
    service.notify('Hello')
  end

  it 'stubs a method' do
    user = instance_double(User, name: 'Alice', email: 'alice@test.com')
    allow(user).to receive(:admin?).and_return(true)
    expect(user.admin?).to be true
  end
end

# --- shared_examples ---
RSpec.shared_examples 'a countable' do
  it 'responds to count' do
    expect(subject).to respond_to(:count)
  end

  it 'has a non-negative count' do
    expect(subject.count).to be >= 0
  end
end

# RSpec.describe Array do
#   it_behaves_like 'a countable'
# end
#
# RSpec.describe Hash do
#   it_behaves_like 'a countable'
# end

# --- Pending / Skip ---
# RSpec.describe 'WIP' do
#   xit 'is skipped' do
#     expect(true).to eq false
#   end
#
#   it 'is pending' do
#     pending 'not implemented yet'
#     expect(some_complex_thing).to be_done
#   end
# end

```
