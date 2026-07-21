export type Project = { id:string; name:string; subject:string; grade:string; textbook_version:string; lesson_topic:string; lesson_count:number; student_profile:string; teacher_requirements:string; status:string; created_at:string; updated_at:string }
export type SourceStatus = 'uploaded'|'parsing'|'indexing'|'ready'|'failed'
export type Source = { id:string; project_id:string; original_name:string; media_type:string; size:number; status:SourceStatus; error_message:string|null; created_at:string; updated_at:string }
export type SearchResult = { content:string; source_id:string; chunk_id:string; filename:string; location:string; score:number }
export type Citation = { source_id:string; chunk_id:string; filename:string; location:string; quote:string }
export type Task = { id:string; project_id:string; type:string; status:'pending'|'running'|'succeeded'|'failed'|'cancelled'; stage:string; progress:number; trace_id:string; result_artifact_id?:string; error_code?:string; error_message?:string; created_at:string; updated_at:string }
export type Artifact = { artifact_id:string; version_id:string; project_id:string; type:'lesson_plan'|'slide_deck'|'speaker_notes'|'exercise_set'; version_no:number; content:Record<string,any>; citations:Citation[]; warnings:string[]; created_at:string }
export type GraphState = { id?:string; status:string; current_node?:string; nodes:Array<{node_id:string;status:string;attempt:number}>; issues:Array<{issue_type:string;target_id:string;severity:string;suggestion:string}> }

