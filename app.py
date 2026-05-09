from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import pandas as pd
import os
from io import BytesIO
import time
import re

app = Flask(__name__)
CORS(app)

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'codes.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Define the model
class QualitativeCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Load the data
comments_data = pd.read_csv('csv/reduced_comments.csv')  # Adjust path as needed

def build_comment_tree(post_id, post_author=None):
    """Build a comment tree but only include comments that have been coded.

    Behavior/assumptions:
    - Only comments that have at least one QualitativeCode entry will be included.
    - If a coded comment's parent is not coded, the coded comment will become a top-level
      entry in the rendered tree (we preserve only coded-comment relationships).
    """
    # Get all comments for this post from the csv
    post_comments = comments_data[comments_data['post_id'] == post_id].copy()

    # If there are no comments in CSV for this post, return empty
    if post_comments.empty:
        return []

    # Find which of these comments have codes saved in the DB
    try:
        post_comment_ids = post_comments['comment_id'].tolist()
        coded_rows = QualitativeCode.query.with_entities(QualitativeCode.comment_id).\
            filter(QualitativeCode.comment_id.in_(post_comment_ids)).distinct().all()
        coded_ids = set(r[0] for r in coded_rows)
    except Exception as e:
        print(f"Error querying coded comment ids for post {post_id}: {e}")
        coded_ids = set()

    # If no coded comments for this post, return empty list (show nothing)
    if not coded_ids:
        return []

    # Keep only coded comments
    post_comments = post_comments[post_comments['comment_id'].isin(coded_ids)].copy()

    # Add is_post_author field using the passed post_author
    if post_author:
        post_comments['is_post_author'] = post_comments['author'] == post_author
    else:
        post_comments['is_post_author'] = False

    # Initialize children list for each comment
    post_comments['children'] = post_comments.apply(lambda x: [], axis=1)

    # Convert to dictionary for easier manipulation
    comments_dict = post_comments.to_dict('records')

    # Build tree structure using only coded comments
    comment_tree = []
    comment_map = {}

    # Map and normalize fields
    for comment in comments_dict:
        # Rename 'comment' to 'body' for template compatibility if present
        if 'comment' in comment:
            comment['body'] = comment.pop('comment')
        else:
            comment['body'] = comment.get('body', '')
        comment_map[comment['comment_id']] = comment

    # Then build the tree: if parent is coded include as child, otherwise top-level
    for comment in comments_dict:
        parent_id = comment.get('parent_id')
        if parent_id in comment_map:
            comment_map[parent_id]['children'].append(comment)
        elif parent_id == post_id or parent_id not in comment_map:
            # Treat as top-level if parent is the post or if parent is not coded
            comment_tree.append(comment)

    # Debug prints (can be removed later)
    print(f"Coded comments for post {post_id}: {len(comments_dict)}")
    print(f"Top-level coded comments: {len(comment_tree)}")

    return comment_tree

@app.route('/')
def index():
    # Get list of available CSV files in the csv directory
    csv_dir = os.path.join(basedir, 'csv')
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]
    def natural_sort_key(s):
        """Sort strings containing numbers naturally"""
        return [int(text) if text.isdigit() else text.lower() 
                for text in re.split(r'(\d+)', s)]
    
    csv_files.sort(key=natural_sort_key)  # Natural sort that handles numbers correctly

    # Get the selected file from query parameter or use default
    selected_file = request.args.get('file', 'topic_1.csv')

    # Make sure the selected file exists, otherwise default to topic_1.csv
    if selected_file not in csv_files:
        selected_file = 'topic_1.csv'

    # Load the selected CSV file
    file_path = os.path.join(csv_dir, selected_file)
    current_posts = pd.read_csv(file_path)

    # Fetch posts that have comments with codes
    posts_with_codes = set()
    try:
        # Get all coded comments
        coded_comments = QualitativeCode.query.with_entities(QualitativeCode.comment_id).distinct().all()
        coded_comment_ids = [cc[0] for cc in coded_comments]
        
        # Filter comments_data to get posts with coded comments
        if coded_comment_ids:
            coded_posts_df = comments_data[comments_data['comment_id'].isin(coded_comment_ids)]
            posts_with_codes = set(coded_posts_df['post_id'].unique())
    except Exception as e:
        print(f"Error fetching coded posts: {str(e)}")

    posts_data = []
    for idx, post in current_posts.iterrows():
        post_data = {
            'index': idx + 1,
            'post_id': post.post_id,
            'title': post.title,
            'flair': post.flair if 'flair' in post else '',
            'created': post.created,
            'url': f"https://reddit.com{post.link}" if 'link' in post else '#',
            'num_comments': post.num_comments if 'num_comments' in post else 0,
            'has_codes': post.post_id in posts_with_codes  # Add this flag
        }
        posts_data.append(post_data)

    return render_template('index.html',
                          posts=posts_data,
                          csv_files=csv_files,
                          selected_file=selected_file)

@app.route('/post/<post_id>')
def view_post(post_id):
    # Get the file parameter or search in all files if not provided
    file_param = request.args.get('file')

    csv_dir = os.path.join(basedir, 'csv')
    post = None # This will store the found post Series

    # --- Search Logic (keep as is) ---
    if file_param:
        # If we know which file to look in, just check that one
        file_path = os.path.join(csv_dir, file_param)
        try:
            temp_df = pd.read_csv(file_path)
            if 'post_id' in temp_df.columns:
                post_match = temp_df[temp_df['post_id'] == post_id]
                if not post_match.empty:
                    post = post_match.iloc[0] # Assign the Series here
        except Exception as e:
            print(f"Error reading specified file {file_path}: {str(e)}")

    # If post not found in the specified file (or no file specified), fall back to searching all files
    if post is None:
        csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]
        for file in csv_files:
            if file == file_param:  # Skip the file we already checked
                continue
            file_path = os.path.join(csv_dir, file)
            try:
                temp_df = pd.read_csv(file_path)
                if 'post_id' in temp_df.columns:
                    post_match = temp_df[temp_df['post_id'] == post_id]
                    if not post_match.empty:
                        post = post_match.iloc[0] # Assign the Series here
                        break
            except Exception as e:
                print(f"Error reading {file}: {str(e)}")
    # --- End Search Logic ---

    if post is None:
        return render_template('error.html', message=f"Post {post_id} not found in any CSV file"), 404

    # Extract author from the found post Series (handle missing author column)
    post_author = post.get('author', None) # Use .get for safety

    # Pass the found author to build_comment_tree
    comment_tree = build_comment_tree(post_id, post_author)

    # Use dictionary access instead of attribute access for safer handling
    post_data = {
        'post_id': post['post_id'],
        'title': post['title'],
        'body': post.get('body', ''), # Use .get for safety
        'created': post.get('created', ''),
        'flair': post.get('flair', ''),
        'url': f"https://reddit.com{post['link']}" if 'link' in post.index else '#',
        'num_comments': post.get('num_comments', 0)
    }

    return render_template('post.html',
                         post=post_data,
                         comments=comment_tree)

@app.route('/save_code', methods=['POST'])
def save_code():
    data = request.json

    if not data or 'comment_id' not in data or 'code' not in data:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    try:
        new_code = QualitativeCode(
            comment_id=data['comment_id'],
            code=data['code']
        )
        db.session.add(new_code)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

from flask import send_file
import csv
from io import StringIO

@app.route('/export_codes')
@app.route('/export_codes/<post_id>')
def export_codes(post_id=None):
    try:
        if (post_id):
            # Get all comment_ids for this post from comments_data
            post_comments = set(comments_data[comments_data['post_id'] == post_id]['comment_id'].tolist())
            # Query codes only for these comments using IN clause
            codes = QualitativeCode.query.filter(QualitativeCode.comment_id.in_(post_comments)).all()
            filename = f'qualitative_codes_post_{post_id}.csv'
        else:
            # Get all codes
            codes = QualitativeCode.query.all()
            filename = 'qualitative_codes_all.csv'

        # Create StringIO object for CSV data
        si = StringIO()
        writer = csv.writer(si)

        # Write header
        writer.writerow(['comment_id', 'code', 'created_at', 'post_id', 'comment_text'])

        # Write data
        for code in codes:
            comment_info = comments_data[comments_data['comment_id'] == code.comment_id]
            if not comment_info.empty:
                comment_row = comment_info.iloc[0]
                writer.writerow([
                    code.comment_id,
                    code.code,
                    code.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    comment_row['post_id'],
                    comment_row['comment']
                ])
            else:
                writer.writerow([
                    code.comment_id,
                    code.code,
                    code.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'N/A',
                    'N/A'
                ])

        # Convert to bytes
        output = si.getvalue().encode('utf-8')
        si.close()

        # Create BytesIO object
        mem = BytesIO()
        mem.write(output)
        mem.seek(0)

        return send_file(
            mem,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"Export error: {str(e)}")  # For debugging
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.cli.command("init-db")
def init_db():
    with app.app_context():
        db.create_all()
        print('Database initialized!')

@app.route('/delete_code/<int:code_id>', methods=['DELETE'])
def delete_code(code_id):
    try:
        code = QualitativeCode.query.get_or_404(code_id)
        db.session.delete(code)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_codes/<comment_id>')
def get_codes(comment_id):
    codes = QualitativeCode.query.filter_by(comment_id=comment_id).all()
    return jsonify({
        'codes': [{
            'id': code.id,
            'code': code.code,
            'created_at': code.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for code in codes]
    })

if __name__ == '__main__':
    app.run(debug=True)
