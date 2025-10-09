# processing/heatmap_generator.py ---

import pandas as pd
import numpy as np
from dtw import dtw
from itertools import combinations
from sklearn.preprocessing import minmax_scale
import seaborn as sns
import matplotlib.pyplot as plt
import os

# --- THIS IS THE CORRECTLY NAMED FUNCTION THAT WAS MISSING ---
def create_summary_curves(summary_df: pd.DataFrame, agg_method: str = 'median') -> dict:
    """
    Parses the summary DataFrame to create a dictionary of summary (mean or median)
    time-series curves for each GROUP.
    """
    summary_curves = {}
    
    # Identify all columns that represent the chosen aggregation of a feature
    suffix = f'_{agg_method}'
    agg_cols = [col for col in summary_df.columns if isinstance(col, str) and col.endswith(suffix)]
    
    if not agg_cols:
        raise ValueError(f"Could not find any columns ending in '{suffix}' in the provided CSV.")

    # Identify factor columns to create a unique group key
    factor_cols = [
        col for col in summary_df.columns 
        if '_mean' not in col and '_median' not in col and '_std' not in col and '_sem' not in col and col != 'time_min' and col != 'n_animals'
    ]
    if not factor_cols:
        raise ValueError("Could not find any factor columns (like group_name) to pivot the data.")
        
    summary_df['unique_group_key'] = summary_df[factor_cols].astype(str).agg(' | '.join, axis=1)

    for agg_col in agg_cols:
        feature_name = agg_col.replace(suffix, '')
        
        # Use pivot_table for robust aggregation
        pivoted = summary_df.pivot_table(
            index='time_min', 
            columns='unique_group_key', 
            values=agg_col,
            aggfunc='mean' # Use mean here as the data is already pre-aggregated to the group level
        )
        
        pivoted = pivoted.ffill().bfill()
        summary_curves[feature_name] = pivoted
        
    return summary_curves
# --- END CORRECTLY NAMED FUNCTION ---

def calculate_univariate_dtw_matrix(feature_df: pd.DataFrame) -> pd.DataFrame:
    """Calculates the DTW distance matrix for a single feature's time-series curves."""
    group_names = list(feature_df.columns)
    num_groups = len(group_names)
    dist_matrix = np.zeros((num_groups, num_groups))

    for i, j in combinations(range(num_groups), 2):
        curve1 = feature_df[group_names[i]].values
        curve2 = feature_df[group_names[j]].values
        
        std1, std2 = np.std(curve1), np.std(curve2)
        curve1_norm = (curve1 - np.mean(curve1)) / std1 if std1 > 0 else curve1 - np.mean(curve1)
        curve2_norm = (curve2 - np.mean(curve2)) / std2 if std2 > 0 else curve2 - np.mean(curve2)
        
        distance = dtw(curve1_norm, curve2_norm, keep_internals=False).distance
        dist_matrix[i, j] = distance
        dist_matrix[j, i] = distance
        
    return pd.DataFrame(dist_matrix, index=group_names, columns=group_names)

def calculate_multivariate_dtw_matrix(summary_curves: dict) -> pd.DataFrame:
    """Calculates a single distance matrix by averaging the scaled distances of all features."""
    first_feature_df = next(iter(summary_curves.values()))
    group_names = list(first_feature_df.columns)
    num_groups = len(group_names)
    final_distance_matrix = np.zeros((num_groups, num_groups))
    
    for feature, feature_df in summary_curves.items():
        univariate_matrix = calculate_univariate_dtw_matrix(feature_df)
        scaled_matrix = minmax_scale(univariate_matrix.values)
        final_distance_matrix += scaled_matrix
        
    if len(summary_curves) > 0:
        final_distance_matrix /= len(summary_curves)
        
    return pd.DataFrame(final_distance_matrix, index=group_names, columns=group_names)

def generate_clustered_heatmap(distance_df: pd.DataFrame, title: str, output_path: str):
    """Takes a distance matrix, generates a clustered heatmap, and saves it."""
    if distance_df.empty:
        print(f"Skipping heatmap generation for '{title}' due to empty distance matrix.")
        return
        
    print(f"Generating heatmap: {title}")
    sns.set_theme(style="white")

    num_groups = len(distance_df)
    if num_groups > 20:
        font_scale = 0.5
    elif num_groups > 12:
        font_scale = 0.7
    else:
        font_scale = 0.8

    font_scale = 1

    sns.set(font_scale=font_scale)
    
    clustermap = sns.clustermap(
        distance_df,
        method='average',
        metric='euclidean',
        cmap='magma_r',
        linewidths=.5,
        figsize=(15, 15)
    )

    plt.setp(clustermap.ax_heatmap.get_xticklabels(), rotation=90)
    plt.setp(clustermap.ax_heatmap.get_yticklabels(), rotation=0)
    clustermap.fig.suptitle(title, y=1.02, fontsize=20)
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    

    
    plt.close('all') # Close all figures to free up memory
