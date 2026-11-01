/* Experimental KROSS 2 v1.2.4, ARM state. Not a ROM exporter.
 * Entry replaces only request 72/18's existing error-table pointer.
 * No boot hook, TG access, allocation, file access or flash operation.
 * All absolute calls are pinned to the application SHA in the builder.
 */
.syntax unified
.arch armv5te
.arm
.text
.balign 4
.global k2_probe_entry
.type k2_probe_entry, %function
k2_probe_entry:
    /* Restore 0x2bf1f4's frame just as its existing tail handlers do. */
    mov r0, r5
    mov r1, r7
    sub sp, fp, #0x20
    ldmia sp, {r4, r5, r6, r7, r8, fp, sp, lr}
    b .Lprobe
.Lprobe:
    push {r4, r5, r6, lr}
    mov r4, r0
    mov r5, r1
    /* Strict USB queue only; other ports must not broadcast a response. */
    cmp r5, #2
    bne .Lreturn
    ldrb r2, [r4]
    cmp r2, #0x72
    bne .Lreturn
    ldrb r2, [r4, #1]
    cmp r2, #0x18
    bne .Lreturn
    ldrb r2, [r4, #4]
    cmp r2, #0
    bne .Lreturn
    ldrb r2, [r4, #5]
    cmp r2, #0
    bne .Lreturn
    /* Only bytes 0..7 survive the real MIDI event queue. */
    sub sp, sp, #16
    mov r0, sp
    ldr ip, .Lheader
    mov lr, pc
    bx ip
    /* F0 42 3g 00 01 49 7D 4B 52 4F 53 45 02 F7 */
    mov r2, #0x7d
    strb r2, [sp, #6]
    mov r2, #0x4b
    strb r2, [sp, #7]
    mov r2, #0x52
    strb r2, [sp, #8]
    mov r2, #0x4f
    strb r2, [sp, #9]
    mov r2, #0x53
    strb r2, [sp, #10]
    mov r2, #0x45
    strb r2, [sp, #11]
    mov r2, #2
    strb r2, [sp, #12]
    mov r2, #0xf7
    strb r2, [sp, #13]
    mov r0, #0
    mov r1, sp
    mov r2, #14
    mov r3, r5
    ldr ip, .Lsend
    mov lr, pc
    bx ip
    add sp, sp, #16
.Lreturn:
    mov r0, #0
    pop {r4, r5, r6, pc}
.balign 4
.Lheader: .word 0xc0138c68
.Lsend: .word 0xc0138240
.size k2_probe_entry, .-k2_probe_entry
