from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SkillInfo:
    id: str
    name: str
    description: str
    required_inputs: tuple[str, ...]


SKILLS = [
    SkillInfo("course_standard_interpretation", "课程标准解读", "从课标资料中提炼本课要求与可追溯依据", ("lesson_topic",)),
    SkillInfo("learning_objectives", "学情与教学目标设计", "设计可观察、可评价且适龄的教学目标", ("grade", "student_profile")),
    SkillInfo("teaching_activities", "教学活动与课堂流程设计", "建立目标—活动—评价一致的课堂流程", ("lesson_count",)),
    SkillInfo("slide_narrative", "课件叙事与页面规划", "规划课堂叙事、页面与逐页讲稿", ("lesson_topic",)),
    SkillInfo("exercise_assessment", "练习与评价设计", "生成基础、巩固、提高练习与评价", ("grade",)),
]


def registry() -> list[dict]:
    return [{"id": s.id, "name": s.name, "description": s.description, "required_inputs": list(s.required_inputs)} for s in SKILLS]


def route_intent(text: str) -> Optional[str]:
    rules = {
        "course_standard_interpretation": ("课标", "课程标准"),
        "learning_objectives": ("目标", "学情"),
        "teaching_activities": ("活动", "流程", "课堂"),
        "slide_narrative": ("课件", "幻灯片", "讲稿"),
        "exercise_assessment": ("练习", "习题", "评价"),
    }
    matches = [skill for skill, words in rules.items() if any(word in text for word in words)]
    return matches[0] if len(matches) == 1 else None
