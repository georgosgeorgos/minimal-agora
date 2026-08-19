"""Manim scenes for minimal-agora architecture diagrams."""

import numpy as np
from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    WHITE,
    Arrow,
    Create,
    CurvedArrow,
    FadeIn,
    GrowArrow,
    Line,
    RoundedRectangle,
    Scene,
    Text,
    VGroup,
)

DARK = "#333333"
BLUE = "#5B9BD5"
GREEN = "#70AD47"
ORANGE = "#ED7D31"
PURPLE = "#7B68AE"
TEAL = "#4ECDC4"
GRAY = "#AAAAAA"
LIGHT_GRAY = "#E8E8E8"
RED = "#E74C3C"


def _box(label, fill, width=2.2, height=0.8):
    rect = RoundedRectangle(
        corner_radius=0.15,
        width=width,
        height=height,
        fill_color=fill,
        fill_opacity=0.3,
        stroke_color=DARK,
        stroke_width=1.5,
    )
    text = Text(label, color=DARK, font_size=22)
    text.move_to(rect.get_center())
    return VGroup(rect, text)


def _arrow(start, end, **kwargs):
    return Arrow(
        start, end,
        color=DARK,
        stroke_width=2,
        tip_length=0.15,
        buff=0.05,
        **kwargs,
    )


class CoreLoop(Scene):
    def construct(self):
        self.camera.background_color = WHITE

        phases = [
            ("Wildcard", BLUE),
            ("Propose", GREEN),
            ("Critique", ORANGE),
            ("Resolve", PURPLE),
            ("Update", TEAL),
        ]

        boxes = [_box(label, color) for label, color in phases]
        done_box = _box("Done?", LIGHT_GRAY, width=1.6, height=0.8)
        classify_box = _box("Classify\nOutcome", GREEN, width=2.0, height=0.9)

        # Row 1: Wildcard → Propose → Critique
        for i, b in enumerate(boxes[:3]):
            b.move_to([(-3.0 + i * 3.0), 1.2, 0])

        # Row 2: Update ← Resolve (right-to-left under row 1)
        boxes[3].move_to([3.0, -1.0, 0])   # Resolve under Critique
        boxes[4].move_to([0.0, -1.0, 0])   # Update in center

        done_box.move_to([-2.5, -1.0, 0])
        classify_box.move_to([-5.2, -1.0, 0])

        arrows = [
            _arrow(boxes[0][0].get_right(), boxes[1][0].get_left()),
            _arrow(boxes[1][0].get_right(), boxes[2][0].get_left()),
            _arrow(boxes[2][0].get_bottom(), boxes[3][0].get_top()),
            _arrow(boxes[3][0].get_left(), boxes[4][0].get_right()),
            _arrow(boxes[4][0].get_left(), done_box[0].get_right()),
        ]

        a_done_classify = _arrow(done_box[0].get_left(), classify_box[0].get_right())
        yes_label = Text("Yes", color=DARK, font_size=16)
        yes_label.next_to(a_done_classify, DOWN, buff=0.05)

        loop_arrow = CurvedArrow(
            done_box[0].get_top(),
            boxes[0][0].get_bottom(),
            angle=1.0,
            color=DARK,
            stroke_width=2,
            tip_length=0.15,
        )
        no_label = Text("No", color=DARK, font_size=16)
        no_label.next_to(loop_arrow.point_from_proportion(0.5), LEFT, buff=0.1)

        for box in boxes:
            self.play(FadeIn(box), run_time=0.3)
        self.play(FadeIn(done_box), FadeIn(classify_box), run_time=0.3)
        for a in arrows:
            self.play(GrowArrow(a), run_time=0.2)
        self.play(GrowArrow(a_done_classify), FadeIn(yes_label), run_time=0.2)
        self.play(Create(loop_arrow), FadeIn(no_label), run_time=0.4)
        self.wait(0.5)


class ParticleFilter(Scene):
    def construct(self):
        self.camera.background_color = WHITE

        title = Text("Particle Filter Resampling", color=DARK, font_size=28)
        title.to_edge(UP, buff=0.4)
        self.play(FadeIn(title), run_time=0.3)

        colors = [RED, BLUE, GREEN, ORANGE]
        labels = ["T1", "T2", "T3", "T4"]
        scores = [0.1, 0.2, 0.5, 0.2]

        x_start, x_mid, x_end = -5.0, -0.5, 5.0
        y_positions = [1.5, 0.5, -0.5, -1.5]

        before_lines = []
        for i, (c, y) in enumerate(zip(colors, y_positions)):
            line = Line(
                np.array([x_start, y, 0]),
                np.array([x_mid - 0.8, y, 0]),
                color=c, stroke_width=3,
            )
            lbl = Text(labels[i], color=c, font_size=18)
            lbl.next_to(line, LEFT, buff=0.1)
            before_lines.append(VGroup(line, lbl))

        for bl in before_lines:
            self.play(Create(bl[0]), FadeIn(bl[1]), run_time=0.25)

        resample_line = Line(
            np.array([x_mid - 0.3, 2.0, 0]),
            np.array([x_mid - 0.3, -2.0, 0]),
            color=GRAY, stroke_width=1.5, stroke_opacity=0.6,
        )
        resample_label = Text("Resample", color=DARK, font_size=20)
        resample_label.next_to(resample_line, UP, buff=0.1)
        self.play(Create(resample_line), FadeIn(resample_label), run_time=0.3)

        score_texts = []
        for i, (s, y) in enumerate(zip(scores, y_positions)):
            st = Text(f"w={s:.1f}", color=DARK, font_size=16)
            st.move_to(np.array([x_mid - 0.3, y + 0.3, 0]))
            score_texts.append(st)
            self.play(FadeIn(st), run_time=0.15)

        self.play(
            before_lines[0][0].animate.set_opacity(0.2),
            before_lines[0][1].animate.set_opacity(0.2),
            score_texts[0].animate.set_opacity(0.2),
            run_time=0.4,
        )

        after_colors = [GREEN, BLUE, GREEN, ORANGE]
        after_labels = ["T3'", "T2", "T3", "T4"]
        after_lines = []
        for i, (c, y, lbl) in enumerate(zip(after_colors, y_positions, after_labels)):
            line = Line(
                np.array([x_mid + 0.2, y, 0]),
                np.array([x_end, y, 0]),
                color=c, stroke_width=3,
            )
            lbl_text = Text(lbl, color=c, font_size=18)
            lbl_text.next_to(line, RIGHT, buff=0.1)
            after_lines.append(VGroup(line, lbl_text))

        for al in after_lines:
            self.play(Create(al[0]), FadeIn(al[1]), run_time=0.25)

        count_text = Text("N=4 in → N=4 out", color=DARK, font_size=20)
        count_text.to_edge(DOWN, buff=0.5)
        self.play(FadeIn(count_text), run_time=0.3)
        self.wait(0.5)


class SimulationModes(Scene):
    def construct(self):
        self.camera.background_color = WHITE

        col_x = [-4.2, 0, 4.2]
        row_y = [3.0, 1.8, 0.3, -1.0, -2.2]

        title_cf = Text("Counterfactual", color=DARK, font_size=24)
        title_pop = Text("Population", color=DARK, font_size=24)
        title_oe = Text("Open-Ended", color=DARK, font_size=24)
        title_cf.move_to([col_x[0], row_y[0], 0])
        title_pop.move_to([col_x[1], row_y[0], 0])
        title_oe.move_to([col_x[2], row_y[0], 0])

        # Column 1: Counterfactual
        scenario_box = _box("Scenario", BLUE, width=2.0, height=0.6)
        scenario_box.move_to([col_x[0], row_y[1], 0])

        runs = []
        for i, lbl in enumerate(["Run 1", "Run 2", "Run N"]):
            b = _box(lbl, GREEN, width=1.2, height=0.5)
            b.move_to([col_x[0] - 1.5 + i * 1.5, row_y[2], 0])
            runs.append(b)

        LIGHT_PURPLE = "#B8A9D4"
        outs = []
        for i, lbl in enumerate(["Out 1", "Out 2", "Out N"]):
            b = _box(lbl, LIGHT_PURPLE, width=1.2, height=0.5)
            b.move_to([col_x[0] - 1.5 + i * 1.5, row_y[3], 0])
            outs.append(b)

        agg = _box("Aggregate", PURPLE, width=2.0, height=0.6)
        agg.move_to([col_x[0], row_y[4], 0])

        # Column 2: Population (skip row_y[3] — no Outs row)
        world = _box("Shared\nWorld", BLUE, width=2.0, height=0.7)
        world.move_to([col_x[1], row_y[1], 0])

        entities = []
        for i, (lbl, c) in enumerate(
            zip(["Pop A", "Pop B", "Pop C"], [GREEN, ORANGE, TEAL])
        ):
            b = _box(lbl, c, width=1.2, height=0.5)
            b.move_to([col_x[1] - 1.3 + i * 1.3, row_y[2], 0])
            entities.append(b)

        judge = _box("Judge", PURPLE, width=2.0, height=0.6)
        judge.move_to([col_x[1], row_y[4], 0])

        # Column 3: Open-Ended (skip row_y[3] — no Outs row)
        single = _box("Single\nTrajectory", BLUE, width=2.0, height=0.7)
        single.move_to([col_x[2], row_y[1], 0])

        fitness = _box("Fitness\nOptimize", GREEN, width=2.0, height=0.7)
        fitness.move_to([col_x[2], row_y[2], 0])

        evolve = _box("Evolve", TEAL, width=2.0, height=0.6)
        evolve.move_to([col_x[2], row_y[4], 0])

        sep1 = Line(
            np.array([-2.1, 3.5, 0]), np.array([-2.1, -2.8, 0]),
            color=GRAY, stroke_width=1, stroke_opacity=0.3,
        )
        sep2 = Line(
            np.array([2.1, 3.5, 0]), np.array([2.1, -2.8, 0]),
            color=GRAY, stroke_width=1, stroke_opacity=0.3,
        )

        all_mobjects = VGroup(
            title_cf, title_pop, title_oe,
            scenario_box, *runs, *outs, agg,
            world, *entities, judge,
            single, fitness, evolve,
            sep1, sep2,
        )
        all_mobjects.move_to([0, 0, 0])

        # Arrows: Scenario → Runs (fan out from bottom edge, not sides)
        cf_arrows = []
        for r in runs:
            cf_arrows.append(_arrow(
                scenario_box[0].get_bottom(),
                r[0].get_top(),
            ))
        # Arrows: Runs → Outs (straight down)
        for r, o in zip(runs, outs):
            cf_arrows.append(_arrow(r[0].get_bottom(), o[0].get_top()))
        # Arrows: Outs → Aggregate (fan in to top edge, not sides)
        for o in outs:
            cf_arrows.append(_arrow(
                o[0].get_bottom(),
                agg[0].get_top(),
            ))

        pop_arrows = []
        for e in entities:
            pop_arrows.append(_arrow(world[0].get_bottom(), e[0].get_top()))
            pop_arrows.append(_arrow(e[0].get_bottom(), judge[0].get_top()))

        oe_arrows = [
            _arrow(single[0].get_bottom(), fitness[0].get_top()),
            _arrow(fitness[0].get_bottom(), evolve[0].get_top()),
        ]
        oe_loop = CurvedArrow(
            evolve[0].get_right(), fitness[0].get_right(),
            angle=-1.5, color=DARK, stroke_width=2, tip_length=0.12,
        )

        self.play(
            FadeIn(title_cf), FadeIn(title_pop), FadeIn(title_oe),
            FadeIn(sep1), FadeIn(sep2),
            run_time=0.3,
        )
        self.play(
            FadeIn(scenario_box), *[FadeIn(r) for r in runs],
            *[FadeIn(o) for o in outs], FadeIn(agg),
            run_time=0.3,
        )
        for a in cf_arrows:
            self.add(a)
        self.play(*[GrowArrow(a) for a in cf_arrows], run_time=0.3)

        self.play(
            FadeIn(world), *[FadeIn(e) for e in entities], FadeIn(judge),
            run_time=0.3,
        )
        for a in pop_arrows:
            self.add(a)
        self.play(*[GrowArrow(a) for a in pop_arrows], run_time=0.3)

        self.play(FadeIn(single), FadeIn(fitness), FadeIn(evolve), run_time=0.3)
        self.play(
            *[GrowArrow(a) for a in oe_arrows],
            Create(oe_loop),
            run_time=0.3,
        )
        self.wait(0.5)


class DataFlow(Scene):
    def construct(self):
        self.camera.background_color = WHITE

        stages = [
            ("Scenario\nYAML", BLUE),
            ("Runner", GREEN),
            ("Board", ORANGE),
            ("Trajectories", PURPLE),
            ("Analysis", TEAL),
        ]
        outputs = [
            ("Report", GREEN),
            ("Plots", ORANGE),
            ("Dashboard", TEAL),
        ]

        stage_boxes = [_box(label, color, width=1.7, height=0.8) for label, color in stages]
        row = VGroup(*stage_boxes).arrange(RIGHT, buff=0.4)
        row.move_to([0, 0.8, 0])

        stage_arrows = []
        for i in range(len(stage_boxes) - 1):
            stage_arrows.append(
                _arrow(stage_boxes[i][0].get_right(), stage_boxes[i + 1][0].get_left())
            )

        output_boxes = [_box(label, color, width=1.5, height=0.6) for label, color in outputs]
        out_group = VGroup(*output_boxes).arrange(RIGHT, buff=0.4)
        out_group.move_to([0, -1.0, 0])

        out_arrows = [
            _arrow(stage_boxes[-1][0].get_bottom(), ob[0].get_top())
            for ob in output_boxes
        ]

        for sb in stage_boxes:
            self.play(FadeIn(sb), run_time=0.2)
        for sa in stage_arrows:
            self.play(GrowArrow(sa), run_time=0.15)
        self.play(*[FadeIn(ob) for ob in output_boxes], run_time=0.3)
        self.play(*[GrowArrow(a) for a in out_arrows], run_time=0.3)
        self.wait(0.5)


class ReviewInterval(Scene):
    def construct(self):
        self.camera.background_color = WHITE

        title = Text("Review Interval Optimization", color=DARK, font_size=28)
        title.to_edge(UP, buff=0.4)
        self.play(FadeIn(title), run_time=0.3)

        phase_names = ["Wildcard", "Propose", "Critique", "Resolve", "Update"]
        phase_colors = [BLUE, GREEN, ORANGE, PURPLE, TEAL]

        # Full review step
        full_label = Text("Full Review Step", color=DARK, font_size=20)
        full_boxes = []
        for i, (name, color) in enumerate(zip(phase_names, phase_colors)):
            b = _box(name, color, width=1.8, height=0.6)
            full_boxes.append(b)
        full_row = VGroup(*full_boxes).arrange(RIGHT, buff=0.4)

        full_label.next_to(full_row, LEFT, buff=0.4)
        full_group = VGroup(full_label, full_row)
        full_group.move_to([0, 1.5, 0])

        full_arrows = []
        for i in range(len(full_boxes) - 1):
            full_arrows.append(
                _arrow(full_boxes[i][0].get_right(), full_boxes[i + 1][0].get_left())
            )

        # Fast step (skip review)
        fast_label = Text("Fast Step (skip review)", color=DARK, font_size=20)
        fast_boxes = []
        for i, (name, color) in enumerate(zip(phase_names, phase_colors)):
            skip = i in (2, 3)
            fill = LIGHT_GRAY if skip else color
            b = _box(name, fill, width=1.8, height=0.6)
            if skip:
                b[0].set_fill(opacity=0.15)
                b[1].set_opacity(0.3)
            fast_boxes.append(b)

        fast_row = VGroup(*fast_boxes).arrange(RIGHT, buff=0.4)
        fast_label.next_to(fast_row, LEFT, buff=0.4)
        fast_group = VGroup(fast_label, fast_row)
        fast_group.move_to([0, -0.5, 0])

        skip_text1 = Text("skip", color=GRAY, font_size=14)
        skip_text1.next_to(fast_boxes[2], DOWN, buff=0.1)
        skip_text2 = Text("skip", color=GRAY, font_size=14)
        skip_text2.next_to(fast_boxes[3], DOWN, buff=0.1)

        fast_arrows = [
            _arrow(fast_boxes[0][0].get_right(), fast_boxes[1][0].get_left()),
            Arrow(
                fast_boxes[1][0].get_right(), fast_boxes[4][0].get_left(),
                color=DARK, stroke_width=2, tip_length=0.12, buff=0.05,
            ),
        ]

        speedup = Text("2-3× faster", color=TEAL, font_size=22)
        speedup.move_to([0, -2.0, 0])

        self.play(FadeIn(full_label), run_time=0.2)
        for b in full_boxes:
            self.play(FadeIn(b), run_time=0.15)
        for a in full_arrows:
            self.play(GrowArrow(a), run_time=0.1)

        self.play(FadeIn(fast_label), run_time=0.2)
        for b in fast_boxes:
            self.play(FadeIn(b), run_time=0.15)
        self.play(FadeIn(skip_text1), FadeIn(skip_text2), run_time=0.2)
        for a in fast_arrows:
            self.play(GrowArrow(a), run_time=0.1)

        self.play(FadeIn(speedup), run_time=0.3)
        self.wait(0.5)
