/** Zod schemas for runtime validation of user input. */

import { z } from "zod";

export const loginRequestSchema = z.object({
  emp_id: z.string().min(1, "Employee ID is required"),
  password: z.string().min(1, "Password is required"),
});

export const punchRequestSchema = z.object({
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  accuracy: z.number().min(0),
});

export const employeeCreateSchema = z.object({
  emp_id: z.string().min(1),
  name: z.string().min(1),
  department: z.string().min(1),
  role: z.enum(["EMPLOYEE", "MANAGER", "HR", "ADMIN"]),
  password: z.string().min(6),
  shift_start_time: z.string(),
  shift_end_time: z.string(),
});

export const officeLocationSchema = z.object({
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
});

export const changePasswordSchema = z
  .object({
    currentPassword: z.string().min(1, "required"),
    newPassword: z
      .string()
      .min(8, "tooShort")
      .max(128, "tooShort")
      .refine((s) => /\d/.test(s), { message: "missingDigit" }),
    confirmPassword: z.string().min(1, "required"),
    empId: z.string().min(1),
  })
  .refine((d) => d.newPassword === d.confirmPassword, {
    path: ["confirmPassword"],
    message: "mismatch",
  })
  .refine((d) => d.newPassword !== d.currentPassword, {
    path: ["newPassword"],
    message: "sameAsCurrent",
  })
  .refine((d) => d.newPassword !== d.empId, {
    path: ["newPassword"],
    message: "sameAsEmpId",
  });

export type LoginRequestInput = z.infer<typeof loginRequestSchema>;
export type PunchRequestInput = z.infer<typeof punchRequestSchema>;
export type EmployeeCreateInput = z.infer<typeof employeeCreateSchema>;
export type OfficeLocationInput = z.infer<typeof officeLocationSchema>;
export type ChangePasswordInput = z.infer<typeof changePasswordSchema>;
