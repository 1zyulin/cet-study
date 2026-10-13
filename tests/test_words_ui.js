'use strict';
// Test the real filtering and review queue with original vocabulary fixtures.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
const start = source.indexOf('function wordBooks(');
const end = source.indexOf('async function wordsView(', start);
assert.ok(start >= 0 && end > start, 'Vocabulary helpers must exist');
const sandbox = vm.createContext({ state: {level:'CET4', wordBook:'', words:[]} });
vm.runInContext(source.slice(start, end), sandbox);
const words = [
  {id:'shared', word:'learn', books:['四级核心词', 'CET6 Essential'], book:'CET6 Essential', due_at:'2025-01-01T00:00:00Z'},
  {id:'cet4', word:'read', book:'CET-4 Practice', due_at:'2030-01-01T00:00:00Z'},
  {id:'cet6', word:'analyse', books:['六级核心词'], due_at:'2025-01-01T00:00:00Z'},
  {id:'custom', word:'home', book:'我的日常词书', due_at:'2025-01-01T00:00:00Z'},
];
const ids = values => values.map(word => word.id).join(',');
assert.equal(ids(sandbox.wordsForStudy(words, '', 'CET4')), 'shared,cet4,custom');
assert.equal(ids(sandbox.wordsForStudy(words, '', 'CET6')), 'shared,cet6,custom');
assert.equal(ids(sandbox.wordsForStudy(words, '四级核心词', 'CET4')), 'shared');
assert.equal(ids(sandbox.wordsForStudy(words, 'CET6 Essential', 'CET6')), 'shared');
assert.equal(ids(sandbox.wordsForStudy(words, 'CET6 Essential', 'CET4')), '');
assert.equal(ids(sandbox.wordsForStudy(words, '不存在的词书', 'CET4')), '');
assert.equal(sandbox.wordBooks({book:'旧版词书', books:[]}).join(','), '旧版词书');
assert.equal(sandbox.wordBooks({books:['四级核心词','四级核心词','']}).join(','), '四级核心词');
assert.equal(sandbox.wordBooks({}).join(','), '未命名词书');
const at = new Date('2026-01-01T00:00:00Z');
const selected = sandbox.wordsForStudy(words, '', 'CET4');
const review = sandbox.wordReviewQueue(selected, at);
assert.equal(ids(review.due), 'shared,custom');
assert.equal(ids(review.queue), 'shared,custom');
const notDue = sandbox.wordReviewQueue(sandbox.wordsForStudy(words, 'CET-4 Practice', 'CET4'), at);
assert.equal(notDue.due.length, 0);
assert.equal(ids(notDue.queue), 'cet4');
assert.equal(sandbox.wordReviewQueue([], at).queue.length, 0);
console.log('Vocabulary filters and review queues passed.');
