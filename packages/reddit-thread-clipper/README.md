# Reddit thread clipper

This disposable proof-of-concept extracts the post and comments already rendered in an open Reddit thread as structured JSON. It runs directly in the browser console and makes no network request to Reddit.

## Usage

1. Open a Reddit thread and wait for it to load.
2. Do not expand anything manually.
3. Open the browser DevTools console.
4. Paste the contents of [poc/extract-thread.js](poc/extract-thread.js) and run it.
5. Read the console summary. It reports the captured comment count and whether expansion stopped because there were no more controls or the safety cap was reached.
6. The script calls the DevTools copy() helper with the JSON result. The full JSON is also logged in the console.

The script uses Reddit's shreddit-* elements and other internal selectors. Those implementation details are unstable, so this is a disposable POC rather than a stable integration contract. It only captures content Reddit rendered before the expansion safety cap.

## Output shape

The script logs and copies structured JSON with `post` first, followed by `comments`. The top-level `comments` array contains the nearest comments. Each comment has `author`, `body`, `permalink`, `score`, and `replies`; `replies` contains that comment's direct child comments recursively.

```json
{
	"post": {
		"author": "post-author",
		"body": "Post body",
		"permalink": "https://www.reddit.com/r/example/comments/post-id/",
		"score": 42,
		"title": "Post title"
	},
	"comments": [
		{
			"author": "comment-author",
			"body": "Top-level comment",
			"permalink": "https://www.reddit.com/r/example/comments/post-id/comment-id/",
			"score": 12,
			"replies": [
				{
					"author": "reply-author",
					"body": "Direct reply",
					"permalink": "https://www.reddit.com/r/example/comments/post-id/reply-id/",
					"score": 3,
					"replies": []
				}
			]
		}
	]
}
```
