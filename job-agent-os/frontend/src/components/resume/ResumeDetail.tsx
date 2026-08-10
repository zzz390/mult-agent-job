"use client";

import {
  Award,
  Briefcase,
  GraduationCap,
  Layers,
  User,
  Wrench,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ResumeResponse, StructuredResumeData } from "@/types/resume";

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase text-muted-foreground">
        {icon}
        {title}
      </div>
      {children}
    </div>
  );
}

export function ResumeDetail({ resume }: { resume: ResumeResponse }) {
  const data = (resume.structured_data ?? {}) as StructuredResumeData;
  const hasStructured =
    data.name ||
    data.education ||
    (data.skills && data.skills.length > 0) ||
    (data.projects && data.projects.length > 0) ||
    (data.internships && data.internships.length > 0);

  return (
    <div className="rounded-xl border bg-card p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold">{resume.title}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            版本 {resume.version}
            {resume.target_direction ? ` · ${resume.target_direction}` : ""}
          </p>
        </div>
        {resume.is_active && <Badge variant="success">活跃</Badge>}
      </div>

      {!hasStructured ? (
        <div className="rounded-lg bg-muted/50 p-4 text-center">
          <p className="text-sm text-muted-foreground">
            该简历暂无结构化数据。
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            上传 Markdown / 文本简历后，Agent 会在匹配流程中自动解析。
          </p>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Basic */}
          {data.name && (
            <Section icon={<User className="h-3.5 w-3.5" />} title="基本信息">
              <p className="text-sm">{data.name}</p>
            </Section>
          )}

          {/* Education */}
          {data.education && (
            <Section icon={<GraduationCap className="h-3.5 w-3.5" />} title="教育经历">
              <div className="rounded-lg bg-muted/40 p-3 text-sm">
                <p className="font-medium">{data.education.school}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {[data.education.degree, data.education.major]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                {data.education.graduation && (
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    毕业时间：{data.education.graduation}
                  </p>
                )}
              </div>
            </Section>
          )}

          {/* Skills */}
          {data.skills && data.skills.length > 0 && (
            <Section icon={<Wrench className="h-3.5 w-3.5" />} title="技能">
              <div className="flex flex-wrap gap-1.5">
                {data.skills.map((s) => (
                  <Badge key={s} variant="secondary">
                    {s}
                  </Badge>
                ))}
              </div>
            </Section>
          )}

          {/* Projects */}
          {data.projects && data.projects.length > 0 && (
            <Section icon={<Layers className="h-3.5 w-3.5" />} title="项目经历">
              <div className="space-y-2">
                {data.projects.map((p, i) => (
                  <div key={i} className="rounded-lg bg-muted/40 p-3">
                    <p className="text-sm font-medium">{p.name}</p>
                    {p.description && (
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                        {p.description}
                      </p>
                    )}
                    {p.tech_stack.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {p.tech_stack.map((t) => (
                          <Badge key={t} variant="outline" className="px-1.5 py-0 text-[10px]">
                            {t}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Internships */}
          {data.internships && data.internships.length > 0 && (
            <Section icon={<Briefcase className="h-3.5 w-3.5" />} title="实习经历">
              <div className="space-y-2">
                {data.internships.map((it, i) => (
                  <div key={i} className="rounded-lg bg-muted/40 p-3">
                    <p className="text-sm font-medium">
                      {it.company}
                      {it.role ? ` · ${it.role}` : ""}
                    </p>
                    {it.duration && (
                      <p className="mt-0.5 text-xs text-muted-foreground">{it.duration}</p>
                    )}
                    {it.description && (
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                        {it.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Certifications */}
          {data.certifications && data.certifications.length > 0 && (
            <Section icon={<Award className="h-3.5 w-3.5" />} title="证书 / 荣誉">
              <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                {data.certifications.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}
