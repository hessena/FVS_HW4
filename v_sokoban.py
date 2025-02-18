#!/usr/bin/env python3


#Usage: python v_sokoban.py <input_board.xsb> <output_directory>

import sys, os, shutil, subprocess, time, re


def gen_in_bounds(expr_x, expr_y):
    # return SMV condition to check if a cell is within board bounds
    return f"({expr_x} >= 0 & {expr_x} < WIDTH & {expr_y} >= 0 & {expr_y} < HEIGHT)"

def gen_not_wall(expr_x, expr_y, walls):
    # return SMV condition to ensure a cell is not a wall
    if not walls:
        return "TRUE"
    conds = []
    for (wx, wy) in walls:
        conds.append(f"!(({expr_x} = {wx}) & ({expr_y} = {wy}))")
    return "(" + " & ".join(conds) + ")"

def gen_not_box(expr_x, expr_y, num_boxes):
    # return SMV condition to ensure a cell is not occupied by any box
    if num_boxes == 0:
        return "TRUE"
    conditions = []
    for i in range(1, num_boxes+1):
        conditions.append(f"(({expr_x} = box_x[{i}]) & ({expr_y} = box_y[{i}]))")
    return "!(" + " | ".join(conditions) + ")"

def gen_free_cell(expr_x, expr_y, walls, num_boxes):
    # cell is free if it is in bounds, not a wall, and not occupied by a box
    return f"({gen_in_bounds(expr_x, expr_y)} & {gen_not_wall(expr_x, expr_y, walls)} & {gen_not_box(expr_x, expr_y, num_boxes)})"

def gen_box_at(expr_x, expr_y, num_boxes):
    # return SMV condition that a box is at a given cell
    if num_boxes == 0:
        return "FALSE"
    conditions = []
    for i in range(1, num_boxes+1):
        conditions.append(f"(({expr_x} = box_x[{i}]) & ({expr_y} = box_y[{i}]))")
    return "(" + " | ".join(conditions) + ")"


def parse_xsb_board(board_path):
    # returns a dictionary with board layout and entity positions
    with open(board_path, "r") as f:
        lines = [line.rstrip("\n") for line in f if line.strip() != ""]
    height = len(lines)
    width = max(len(line) for line in lines)
    board = []
    walls = set()
    targets = []
    boxes = []
    player = None
    for y, line in enumerate(lines):
        # pad the row to make all rows have the same width
        row = list(line.ljust(width))
        board.append(row)
        for x, ch in enumerate(row):
            if ch == '#':
                walls.add((x, y))
            elif ch in ['.', '+', '*']:
                targets.append((x, y))
            if ch in ['$', '*']:
                boxes.append((x, y))
            if ch in ['@', '+']:
                player = (x, y)
    return {"board": board, "width": width, "height": height, "walls": walls,
            "targets": targets, "boxes": boxes, "player": player}


def generate_smv_model(parsed_board):
    width    = parsed_board["width"]
    height   = parsed_board["height"]
    walls    = parsed_board["walls"]
    targets  = parsed_board["targets"]
    boxes    = parsed_board["boxes"]
    player   = parsed_board["player"]
    num_boxes = len(boxes)
    targets.sort(key=lambda pos: (pos[1], pos[0]))

    smv_lines = []
    smv_lines.append("-- Automatically generated SMV model for Sokoban")
    smv_lines.append("MODULE main")
    smv_lines.append("CONSTANTS")
    smv_lines.append(f"    WIDTH := {width};")
    smv_lines.append(f"    HEIGHT := {height};")
    smv_lines.append(f"    NUM_BOXES := {num_boxes};")
    smv_lines.append("")
    smv_lines.append("VAR")
    smv_lines.append("    player_x : 0..WIDTH-1;")
    smv_lines.append("    player_y : 0..HEIGHT-1;")
    smv_lines.append("    box_x : array 1..NUM_BOXES of 0..WIDTH-1;")
    smv_lines.append("    box_y : array 1..NUM_BOXES of 0..HEIGHT-1;")
    smv_lines.append("    move : {l, r, u, d, L, R, U, D};")
    smv_lines.append("")
    smv_lines.append("ASSIGN")

    # initialize player's position
    smv_lines.append(f"    init(player_x) := {player[0]};")
    smv_lines.append(f"    init(player_y) := {player[1]};")

    # initialize each box's position
    for i, (bx, by) in enumerate(boxes, start=1):
        smv_lines.append(f"    init(box_x[{i}]) := {bx};")
        smv_lines.append(f"    init(box_y[{i}]) := {by};")
    smv_lines.append("")
    
    # calculate conditions for simple moves
    free_left  = gen_free_cell("player_x - 1", "player_y", walls, num_boxes)
    free_right = gen_free_cell("player_x + 1", "player_y", walls, num_boxes)
    free_up    = gen_free_cell("player_x", "player_y - 1", walls, num_boxes)
    free_down  = gen_free_cell("player_x", "player_y + 1", walls, num_boxes)
    
    # calculate conditions for push moves
    push_left  = f"({gen_box_at('player_x - 1', 'player_y', num_boxes)} & {gen_free_cell('player_x - 2', 'player_y', walls, num_boxes)})"
    push_right = f"({gen_box_at('player_x + 1', 'player_y', num_boxes)} & {gen_free_cell('player_x + 2', 'player_y', walls, num_boxes)})"
    push_up    = f"({gen_box_at('player_x', 'player_y - 1', num_boxes)} & {gen_free_cell('player_x', 'player_y - 2', walls, num_boxes)})"
    push_down  = f"({gen_box_at('player_x', 'player_y + 1', num_boxes)} & {gen_free_cell('player_x', 'player_y + 2', walls, num_boxes)})"
    
    # set next state for the x-coordinate of the player based on move
    smv_lines.append("    next(player_x) := case")
    smv_lines.append(f"        move = l & {free_left} : player_x - 1;")
    smv_lines.append(f"        move = r & {free_right} : player_x + 1;")
    smv_lines.append(f"        move = u & {free_up} : player_x;")
    smv_lines.append(f"        move = d & {free_down} : player_x;")
    smv_lines.append(f"        move = L & {push_left} : player_x - 1;")
    smv_lines.append(f"        move = R & {push_right} : player_x + 1;")
    smv_lines.append(f"        move = U & {push_up} : player_x;")
    smv_lines.append(f"        move = D & {push_down} : player_x;")
    smv_lines.append("        TRUE : player_x;")
    smv_lines.append("    esac;")
    smv_lines.append("")

    # set next state for the y-coordinate of the player based on move
    smv_lines.append("    next(player_y) := case")
    smv_lines.append(f"        move = l & {free_left} : player_y;")
    smv_lines.append(f"        move = r & {free_right} : player_y;")
    smv_lines.append(f"        move = u & {free_up} : player_y - 1;")
    smv_lines.append(f"        move = d & {free_down} : player_y + 1;")
    smv_lines.append(f"        move = L & {push_left} : player_y;")
    smv_lines.append(f"        move = R & {push_right} : player_y;")
    smv_lines.append(f"        move = U & {push_up} : player_y - 1;")
    smv_lines.append(f"        move = D & {push_down} : player_y + 1;")
    smv_lines.append("        TRUE : player_y;")
    smv_lines.append("    esac;")
    smv_lines.append("")
    
    # set next state for the box after a push move
    for i in range(1, num_boxes+1):
        # update for x-coordinate if pushed horizontally
        smv_lines.append(f"    next(box_x[{i}]) := case")
        smv_lines.append(f"        move = L & (box_x[{i}] = player_x - 1 & box_y[{i}] = player_y) & {gen_free_cell('player_x - 2', 'player_y', walls, num_boxes)} : box_x[{i}] - 1;")
        smv_lines.append(f"        move = R & (box_x[{i}] = player_x + 1 & box_y[{i}] = player_y) & {gen_free_cell('player_x + 2', 'player_y', walls, num_boxes)} : box_x[{i}] + 1;")
        smv_lines.append(f"        TRUE : box_x[{i}];")
        smv_lines.append("    esac;")

        # update for y-coordinate if pushed vertically
        smv_lines.append(f"    next(box_y[{i}]) := case")
        smv_lines.append(f"        move = U & (box_x[{i}] = player_x & box_y[{i}] = player_y - 1) & {gen_free_cell('player_x', 'player_y - 2', walls, num_boxes)} : box_y[{i}] - 1;")
        smv_lines.append(f"        move = D & (box_x[{i}] = player_x & box_y[{i}] = player_y + 1) & {gen_free_cell('player_x', 'player_y + 2', walls, num_boxes)} : box_y[{i}] + 1;")
        smv_lines.append(f"        TRUE : box_y[{i}];")
        smv_lines.append("    esac;")
        smv_lines.append("")
    
    # the winning condition - each box must be on its corresponding target
    win_conditions = []
    for i, (tx, ty) in enumerate(targets[:num_boxes], start=1):
        win_conditions.append(f"(box_x[{i}] = {tx} & box_y[{i}] = {ty})")
    smv_lines.append("DEFINE")
    smv_lines.append("    win := " + " & ".join(win_conditions) + ";")
    smv_lines.append("")
    
    # LTL specification to eventually reach a winning state
    smv_lines.append("-- LTL specification: eventually reach a winning state")
    smv_lines.append("LTLSPEC")
    smv_lines.append("    F win")
    smv_lines.append("")
    
    return "\n".join(smv_lines)


def write_command_file(smv_filename, engine, cmd_filename):
    commands = []
    commands.append(f"set engine {engine}")
    commands.append("go")
    commands.append('check_ltlspec -p "F win"')
    commands.append("quit")
    with open(cmd_filename, "w") as f:
        f.write("\n".join(commands))

def run_nuxmv(smv_file, engine, output_path):
    NUXMV_PATH = "C:\\Users\\Omri Anchi\\Downloads\\nuXmv-2.1.0-win64\\nuXmv-2.1.0-win64\\bin"
    cmd_filename = os.path.join(os.path.dirname(output_path), f"nuxmv_{engine}.cmd")
    write_command_file(smv_file, engine, cmd_filename)
    cmd = [NUXMV_PATH, "-source", cmd_filename, smv_file]
    start_time = time.time()
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True, check=True)
        output = proc.stdout
    except subprocess.CalledProcessError as e:
        output = e.stdout
    runtime = time.time() - start_time
    with open(output_path, "w") as f:
        f.write(output)
    return output, runtime

import re

def extract_solution(nuxmv_output):
    match = re.search(r"Solution:\s*LURD moves:\s*([lurdLURD]+)", nuxmv_output)
    if match:
        return match.group(1)

    lurds = []
    for line in nuxmv_output.split("\n"):
        if "move =" in line:
            move = line.split("=")[-1].strip()
            if move in "lurdLURD":
                lurds.append(move)

    if lurds:
        return "".join(lurds)

    return None


def main():
    if len(sys.argv) != 3:
        print("Usage: python v_sokoban.py <input_board.xsb> <output_directory>")
        sys.exit(1)
    
    input_board = sys.argv[1]
    output_dir  = sys.argv[2]
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    board_copy_path = os.path.join(output_dir, os.path.basename(input_board))
    shutil.copy(input_board, board_copy_path)
    
    parsed_board = parse_xsb_board(input_board)
    
    smv_model = generate_smv_model(parsed_board)
    smv_filename = os.path.join(output_dir, "board.smv")
    with open(smv_filename, "w") as f:
        f.write(smv_model)
    
    nuxmv_outputs = {}
    runtimes = {}
    for engine in ["bdd", "sat"]:
        output_path = os.path.join(output_dir, f"nuxmv_{engine}.out")
        print(f"Running nuXmv with engine {engine}...")
        output, rt = run_nuxmv(smv_filename, engine, output_path)
        nuxmv_outputs[engine] = output
        runtimes[engine] = rt
        print(f"nuXmv ({engine}) finished in {rt:.2f} seconds. Output saved to {output_path}.")
    
    solution = extract_solution(nuxmv_outputs["bdd"])
    if solution is None:
        solution_text = "There is no solution."
    else:
        solution_text = solution
    
    print("Extracted solution:", repr(solution_text))  

    sol_filename = os.path.join(output_dir, "solution.txt")
    with open(sol_filename, "w") as f:
        f.write(solution_text + "\n")
        f.write(f"BDD engine runtime: {runtimes['bdd']:.2f} seconds\n")
        f.write(f"SAT engine runtime: {runtimes['sat']:.2f} seconds\n")
        f.write("Runtime improvement: Using nuXmv command files minimized startup overhead.\n")
    
    print(f"Solution file saved to {sol_filename}")


if __name__ == '__main__':
    main()
