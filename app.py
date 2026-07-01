import json
import os
import random
import math
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

@app.route('/')
def index():
    """Serves the main HTML page"""
    return send_file('index.html')

LOTTERY_DIR = 'lotteries'

# ==========================================
# 1. THE MATH ENGINES (Copied from your scripts)
# ==========================================

def score_set(numbers, freq_dict):
    return sum(freq_dict[str(n)] for n in numbers)

def generate_pg25_geometry():
    affine_points = [(x, y, 1) for x in range(5) for y in range(5)]
    infinity_points = [(1, 0, 0), (0, 1, 0), (1, 1, 0), (1, 2, 0), (1, 3, 0), (1, 4, 0)]
    all_points = affine_points + infinity_points
    lines = []
    seen_lines = set()
    for a in range(5):
        for b in range(5):
            for c in range(5):
                if a == 0 and b == 0 and c == 0: continue
                if a != 0: inv = pow(a, -1, 5); na, nb, nc = (a*inv)%5, (b*inv)%5, (c*inv)%5
                elif b != 0: inv = pow(b, -1, 5); na, nb, nc = (a*inv)%5, (b*inv)%5, (c*inv)%5
                else: inv = pow(c, -1, 5); na, nb, nc = (a*inv)%5, (b*inv)%5, (c*inv)%5
                if (na, nb, nc) in seen_lines: continue
                seen_lines.add((na, nb, nc))
                pts_on_line = [p for p in all_points if (na*p[0] + nb*p[1] + nc*p[2]) % 5 == 0]
                if len(pts_on_line) == 6: lines.append(pts_on_line)
    return affine_points, infinity_points, lines

def run_pg25_engine(freq_dict, iterations=5000):
    affine_pts, inf_pts, lines = generate_pg25_geometry()
    hot_numbers = sorted(freq_dict.keys(), key=lambda x: freq_dict[x], reverse=True)[:31]
    
    best_total_score = -1
    best_sets = None
    best_mapping = None
    
    for _ in range(iterations):
        shuffled_nums = hot_numbers.copy()
        random.shuffle(shuffled_nums)
        mapping = dict(zip(affine_pts + inf_pts, shuffled_nums))
        
        current_lines = []
        for line in lines:
            nums = sorted([mapping[p] for p in line])
            sc = score_set(nums, freq_dict)
            current_lines.append((nums, sc))
            
        current_lines.sort(key=lambda x: x[1], reverse=True)
        top_6 = current_lines[:6]
        total_score = sum(s for _, s in top_6)
        
        if total_score > best_total_score:
            best_total_score = total_score
            best_sets = top_6
            best_mapping = mapping
            
    return best_sets, best_mapping, hot_numbers

def run_weighted_grid_engine(freq_dict, pick_size, bonus_configs, num_sets=6, pool_size=35, max_overlap=2):
    sorted_main = sorted(freq_dict.keys(), key=lambda x: freq_dict[x], reverse=True)[:pool_size]
    main_weights = [freq_dict[n] for n in sorted_main]
    
    final_sets = []
    used_main = set()
    
    while len(final_sets) < num_sets:
        combo = set()
        while len(combo) < pick_size:
            combo.add(random.choices(sorted_main, weights=main_weights, k=1)[0])
            
        combo_list = sorted(list(combo))
        if len(combo.intersection(used_main)) > max_overlap: continue
            
        bonus_results = []
        for bonus in bonus_configs:
            b_pool = list(bonus['frequencies'].keys())
            b_weights = [bonus['frequencies'][n] for n in b_pool]
            b_combo = set()
            while len(b_combo) < bonus['pick_size']:
                b_combo.add(random.choices(b_pool, weights=b_weights, k=1)[0])
            bonus_results.append({"name": bonus['name'], "numbers": sorted(list(b_combo)), "color": bonus['color']})
            
        final_sets.append((combo_list, bonus_results))
        used_main.update(combo)
        
    return final_sets, sorted_main

# ==========================================
# 2. THE VISUALIZER COORDINATE CALCULATOR
# ==========================================

def calculate_canvas_data(hot_pool, freq_dict, shape, best_sets, best_mapping=None):
    """Replaces Tkinter drawing by calculating X/Y coordinates for the browser"""
    canvas_size = 450
    margin = 60
    points_data = []
    lines_data = []
    
    if shape == "pg25":
        affine_pts, inf_pts, _ = generate_pg25_geometry()
        grid_space = (canvas_size - margin * 2) / 4
        coords = {}
        
        # Grid points
        for p in affine_pts:
            x = margin + (p[0] * grid_space)
            y = margin + (p[1] * grid_space)
            coords[p] = (x, y)
            
        # Circle points
        circle_center = canvas_size / 2
        circle_radius = canvas_size / 2 - 20
        for i, p in enumerate(inf_pts):
            angle = math.radians(i * 60 - 90)
            x = circle_center + circle_radius * math.cos(angle)
            y = circle_center + circle_radius * math.sin(angle)
            coords[p] = (x, y)
            
        # Map numbers to coordinates
        for num in hot_pool:
            for p, (x, y) in coords.items():
                if best_mapping[p] == num:
                    points_data.append({"id": num, "x": x, "y": y, "freq": freq_dict[str(num)]})
                    break
                    
        # Map lines
        line_colors = ['#ff4d4d', '#4dff88', '#ffff4d', '#4d4dff', '#ff4dff', '#4dffff']
        for idx, (combo, score) in enumerate(best_sets):
            for line in generate_pg25_geometry()[2]:
                if sorted([best_mapping[p] for p in line]) == combo:
                    lines_data.append({"color": line_colors[idx], "point_ids": combo, "bonus": []})
                    break

    else: # Weighted Grids (open or closed polygons)
        grid_points = [(x, y) for y in range(7) for x in range(5)]
        x_space = (canvas_size - margin * 2) / 4
        y_space = (canvas_size - margin * 2) / 6
        
        coords = {}
        for num, (gx, gy) in zip(hot_pool, grid_points):
            x = margin + (gx * x_space)
            y = margin + (gy * y_space)
            coords[num] = (x, y)
            points_data.append({"id": num, "x": x, "y": y, "freq": freq_dict[str(num)]})
            
        line_colors = ['#ff4d4d', '#4dff88', '#ffff4d', '#4d4dff', '#ff4dff', '#4dffff']
        for idx, (combo, bonus_results) in enumerate(best_sets):
            bonus_coords = []
            for b_res in bonus_results:
                pts = [coords[n] for n in combo]
                center_x = sum(p[0] for p in pts) / len(pts)
                center_y = sum(p[1] for p in pts) / len(pts)
                
                if len(b_res['numbers']) == 1:
                    bonus_coords.append({"id": b_res['numbers'][0], "x": center_x, "y": center_y, "color": b_res['color']})
                elif len(b_res['numbers']) == 2: # EuroMillions offset
                    offset = 18
                    bonus_coords.append({"id": b_res['numbers'][0], "x": center_x - offset, "y": center_y - offset, "color": b_res['color']})
                    bonus_coords.append({"id": b_res['numbers'][1], "x": center_x + offset, "y": center_y + offset, "color": b_res['color']})
                    
            lines_data.append({"color": line_colors[idx], "point_ids": combo, "bonus": bonus_coords})

    return points_data, lines_data

# ==========================================
# 3. THE WEB API ENDPOINTS
# ==========================================

@app.route('/api/lotteries', methods=['GET'])
def get_lotteries():
    """Returns a list of available lotteries for the dropdown menu"""
    files = [f.replace('.json', '') for f in os.listdir(LOTTERY_DIR) if f.endswith('.json')]
    return jsonify(files)

@app.route('/api/generate', methods=['POST'])
def generate_sets():
    """The main engine: Takes a lottery name, runs the math, returns JSON"""
    data = request.json
    lottery_id = data.get('lottery_id')
    
    file_path = os.path.join(LOTTERY_DIR, f"{lottery_id}.json")
    if not os.path.exists(file_path):
        return jsonify({"error": "Lottery not found"}), 404

    with open(file_path, 'r') as f:
        config = json.load(f)

    freq_dict = config['frequencies']
    shape = config['visualizer_shape']
    pick_size = config['main_pick_size']
    bonus_configs = config.get('bonus_balls', [])

    # Dynamic overlap rules based on set size
    max_overlap = 2 if pick_size <= 5 else 3

    # Route to correct math engine
    if config['draw_type'] == 'pg25_geometry':
        best_sets_raw, best_mapping, hot_pool = run_pg25_engine(freq_dict)
        final_sets_output = []
        for combo, score in best_sets_raw:
            final_sets_output.append({"main": combo, "bonus": [], "score": score})
        points, lines = calculate_canvas_data(hot_pool, freq_dict, shape, best_sets_raw, best_mapping)
    else:
        best_sets_raw, hot_pool = run_weighted_grid_engine(freq_dict, pick_size, bonus_configs, max_overlap=max_overlap)
        final_sets_output = []
        for combo, bonus_results in best_sets_raw:
            score = score_set(combo, freq_dict)
            final_sets_output.append({"main": combo, "bonus": bonus_results, "score": score})
        points, lines = calculate_canvas_data(hot_pool, freq_dict, shape, best_sets_raw)

    return jsonify({
        "name": config['name'],
        "shape": shape,
        "sets": final_sets_output,
        "canvas": {
            "points": points,
            "lines": lines
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
