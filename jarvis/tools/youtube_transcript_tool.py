"""Fetch a YouTube video's transcript (free, no API key — auto-captions via
youtube-transcript-api) so it can be summarized before watching."""
from __future__ import annotations

from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

from tools.base import Tool


class GetYoutubeTranscriptTool(Tool):
    name = "get_youtube_transcript"
    description = (
        "Get the transcript of a YouTube video by its video_id (from search_youtube or a "
        "URL like youtube.com/watch?v=VIDEO_ID), for summarizing before watching."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "video_id": {"type": "string"},
            "max_chars": {"type": "integer", "description": "Default 8000."},
        },
        "required": ["video_id"],
    }

    def run(self, video_id: str, max_chars: int = 8000) -> str:
        try:
            transcript = YouTubeTranscriptApi().fetch(video_id)
        except (TranscriptsDisabled, NoTranscriptFound):
            return "No transcript/captions available for this video."

        text = " ".join(segment.text for segment in transcript)
        return text[:max_chars]
